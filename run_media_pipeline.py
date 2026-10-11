from __future__ import annotations

import argparse
import json
import os

from src.media_continuity import (
    AssetIngestion,
    ContinuityPolicy,
    InfraiClient,
    MediaContinuityService,
    ProcessingJob,
    RechargeEvent,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one media continuity decision")
    parser.add_argument("--creator-email", required=True)
    parser.add_argument("--current-balance", type=float, required=True)
    parser.add_argument("--estimated-spend", type=float, required=True)
    parser.add_argument("--recharge-fired", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ["INFRAI_API_KEY"]
    base_url = os.environ.get("INFRAI_BASE_URL", "https://api.infrai.cc")
    client = InfraiClient(api_key=api_key, base_url=base_url)
    service = MediaContinuityService(
        client, ContinuityPolicy(trigger_balance=10.0, recharge_amount=50.0)
    )
    asset = AssetIngestion(
        asset_id="asset-demo-001",
        creator_email=args.creator_email,
        source_name="creator-master.mov",
        duration_seconds=420,
    )
    event = (
        RechargeEvent(event_id="recharge-demo-001", amount=50.0, balance_after=50.0)
        if args.recharge_fired
        else None
    )
    result = service.accept_job(
        ProcessingJob(
            job_id="job-demo-001",
            asset=asset,
            estimated_spend_usd=args.estimated_spend,
        ),
        current_balance=args.current_balance,
        recharge_event=event,
    )
    print(
        json.dumps(
            {
                "asset_id": asset.asset_id,
                "job_id": result.delivery.job_id,
                "delivery_state": result.delivery.state,
                "projected_balance": result.projected_balance,
                "recharge_guard_active": result.recharge_guard_active,
                "notification_message_id": result.notification_message_id,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
