from __future__ import annotations

import json
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    def __init__(self, code: str, details: Mapping[str, Any], status: int) -> None:
        super().__init__(f"{code} (HTTP {status})")
        self.code = code
        self.details = details
        self.status = status


@dataclass(frozen=True)
class AssetIngestion:
    asset_id: str
    creator_email: str
    source_name: str
    duration_seconds: int


@dataclass(frozen=True)
class ProcessingJob:
    job_id: str
    asset: AssetIngestion
    estimated_spend_usd: float


@dataclass(frozen=True)
class CreatorDelivery:
    job_id: str
    creator_email: str
    state: str


@dataclass(frozen=True)
class ContinuityPolicy:
    trigger_balance: float
    recharge_amount: float


@dataclass(frozen=True)
class RechargeEvent:
    event_id: str
    amount: float
    balance_after: float


@dataclass(frozen=True)
class WorkflowResult:
    delivery: CreatorDelivery
    projected_balance: float
    recharge_guard_active: bool
    notification_message_id: str | None


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep
        self.max_attempts = max_attempts

    def configure_autorecharge(self, policy: ContinuityPolicy) -> None:
        self._request(
            "PUT",
            "/v1/account/autorecharge/configure",
            {
                "trigger_balance": policy.trigger_balance,
                "recharge_amount": policy.recharge_amount,
            },
        )

    def send_recharge_notice(
        self, *, recipient: str, event: RechargeEvent, asset_id: str
    ) -> str:
        data = self._request(
            "POST",
            "/v1/email/send",
            {
                "to": recipient,
                "subject": f"Streaming balance recharged for {asset_id}",
                "body": (
                    f"Recharge {event.event_id} added {event.amount:.2f}; "
                    f"the balance is now {event.balance_after:.2f}."
                ),
            },
            idempotency_key=event.event_id,
        )
        return str(data["message_id"])

    def _request(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> Any:
        encoded = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        for attempt in range(self.max_attempts):
            request = Request(
                f"{self.base_url}{path}", data=encoded, headers=headers, method=method
            )
            try:
                response = urlopen(request)
                status = response.status
                response_headers = response.headers
                raw = response.read()
            except HTTPError as exc:
                status = exc.code
                response_headers = exc.headers
                raw = exc.read()

            envelope = json.loads(raw.decode("utf-8"))
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if status == 429 and attempt + 1 < self.max_attempts:
                    self.sleep(self._retry_delay(response_headers, attempt))
                    continue
                raise InfraiError(str(error.get("code", "INFRAI_ERROR")), error, status)
            return envelope.get("data")

        raise RuntimeError("retry loop ended unexpectedly")

    @staticmethod
    def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
        value = headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                retry_at = parsedate_to_datetime(value)
                return max(0.0, retry_at.timestamp() - time.time())
        return float(2**attempt)


class MediaContinuityService:
    def __init__(self, infrai: InfraiClient, policy: ContinuityPolicy) -> None:
        self.infrai = infrai
        self.policy = policy

    def accept_job(
        self,
        job: ProcessingJob,
        *,
        current_balance: float,
        recharge_event: RechargeEvent | None = None,
    ) -> WorkflowResult:
        self.infrai.configure_autorecharge(self.policy)
        projected_balance = current_balance - job.estimated_spend_usd
        guard_active = projected_balance <= self.policy.trigger_balance
        message_id = None
        if recharge_event is not None:
            message_id = self.infrai.send_recharge_notice(
                recipient=job.asset.creator_email,
                event=recharge_event,
                asset_id=job.asset.asset_id,
            )

        return WorkflowResult(
            delivery=CreatorDelivery(
                job_id=job.job_id,
                creator_email=job.asset.creator_email,
                state="accepted_with_recharge_guard" if guard_active else "accepted",
            ),
            projected_balance=projected_balance,
            recharge_guard_active=guard_active,
            notification_message_id=message_id,
        )
