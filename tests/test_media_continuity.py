from src.media_continuity import (
    AssetIngestion,
    ContinuityPolicy,
    MediaContinuityService,
    ProcessingJob,
    RechargeEvent,
)


class RecordingInfrai:
    def __init__(self) -> None:
        self.policy = None
        self.notice = None

    def configure_autorecharge(self, policy: ContinuityPolicy) -> None:
        self.policy = policy

    def send_recharge_notice(
        self, *, recipient: str, event: RechargeEvent, asset_id: str
    ) -> str:
        self.notice = (recipient, event.event_id, asset_id)
        return "msg-test-001"


def test_low_balance_job_is_accepted_and_recharge_event_notifies_creator() -> None:
    infrai = RecordingInfrai()
    service = MediaContinuityService(
        infrai, ContinuityPolicy(trigger_balance=10.0, recharge_amount=50.0)
    )
    asset = AssetIngestion(
        asset_id="asset-7",
        creator_email="creator@example.com",
        source_name="launch-film.mov",
        duration_seconds=180,
    )

    result = service.accept_job(
        ProcessingJob(job_id="job-7", asset=asset, estimated_spend_usd=4.0),
        current_balance=12.0,
        recharge_event=RechargeEvent(
            event_id="recharge-7", amount=50.0, balance_after=58.0
        ),
    )

    assert result.delivery.state == "accepted_with_recharge_guard"
    assert result.projected_balance == 8.0
    assert result.notification_message_id == "msg-test-001"
    assert infrai.policy == ContinuityPolicy(trigger_balance=10.0, recharge_amount=50.0)
    assert infrai.notice == ("creator@example.com", "recharge-7", "asset-7")
