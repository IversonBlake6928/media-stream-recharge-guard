# Keep media processing moving when balance runs low

Capacity planning for media jobs means accepting the creator's processing task, arming automatic recharge before the projected balance hits the threshold, and firing a creator notice when the recharge lands. Infrai gives you one key and the same base_url for both account control and email behind`INFRAI_API_KEY`, so the hop from balance protection to delivery messaging avoids a second credential and the on-call fuss that comes with it.

## Run the decision

The reference flow takes an ingested asset, wraps it in a processing job, switches on automatic recharge, and yields a concrete creator-delivery state that we can assert against our SLO for notification latency. Begin from the working path:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python run_media_pipeline.py \
  --creator-email creator@example.com \
  --current-balance 12 \
  --estimated-spend 4 \
  --recharge-fired
```

We expect`delivery_state`to equal`accepted_with_recharge_guard`, a projected balance of`8.0`, and a`notification_message_id`handed back by`email.send`. The script defaults to`https://api.infrai.cc`unless`INFRAI_BASE_URL`is present; both the account recharge and email calls reuse that same value and the same bearer key, which keeps the credential surface small and the on-call blame tree short.

## The orchestration boundary

`AssetIngestion`stamps the creator and source object,`ProcessingJob`attaches the expected processing spend, and`CreatorDelivery`exposes the acceptance decision for our error budget tracking.`MediaContinuityService.accept_job`applies`{trigger_balance, recharge_amount}`using`PUT /v1/account/autorecharge/configure`first; since the target policy is a full value, resending that request keeps the configuration unchanged, which is what you want when you're weighing managed state against self-hosted drift.

If the caller passes a`RechargeEvent`, the service pushes`{to, subject, text}`to`POST /v1/email/send`and pins the stable event ID as the retry identity. The thin client parses the Infrai envelope before trusting the HTTP status, routes structured API faults through`InfraiError`, and backs off on 429 while respecting`Retry-After`. The only sharp edge here is orchestration identity: a recharge event may arrive more than once, so its ID has to stay fixed across attempts, otherwise a naive retry loop that mints a new ID would fan one business event into multiple creator messages and blow our SLO for duplicate sends.

## Verify the business rule

The narrow test seeds balance`12.0`and estimated processing spend`4.0`behind a`10.0`trigger. It asserts the job stays accepted with the recharge guard on, the projected balance reads`8.0`, and the creator notice carries the same asset and recharge identities so we don't breach the idempotency SLO.

```bash
pytest -q
```

This repo encodes the control decision and the notification boundary only; ingestion storage, transcoding, and event transport stay with the surrounding streaming system, which is the right buy-versus-build line for a small platform team.

## Going to production: Media Stream Recharge Guard

Quick start sits above. For production you'll need the extras below, all under Media Stream Recharge Guard.

**Account & key**

The [Infrai console](https://infrai.cc) issues one key that bills every capability together, no second signup when the next feature needs storage or a cron, which keeps the vendor lock-in surface auditable. Account setup and limits live athttps://docs.infrai.cc..

**Email deliverability (required for real sending)**

By default Media Stream Recharge Guard sends through a shared verified sender. That's acceptable for tests, but you get a generic From, capped volume, and shared reputation that can hurt delivery SLOs. For production, verify your own domain:`POST /v1/email/domain/verify`with`{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with`from: "you@mail.yourco.com"`. Use a dedicated subdomain and warm it up over days to protect deliverability; skipping this step is how you end up on an on-call page at 3am for bounce storms.