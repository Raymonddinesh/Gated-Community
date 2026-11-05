# ADR 007: Asynchronous Jobs & Multi-Channel Notification Strategy

## Status
Accepted

## Context
Society management demands extensive background processing: monthly recurring billing batch generation, midnight overdue penalty calculations, automated gate pass expiration, and multi-channel notifications (Push, SMS, WhatsApp, Email). 
Executing these operations in the main HTTP request/response loop impairs API responsiveness and risks timeouts.

## Decision
1. **Queue Architecture**:
   - **BullMQ on Redis** for resilient background task queueing and distributed job scheduling.
2. **Dedicated Queues**:
   - `queue:notifications`: In-app WebSocket alerts, FCM/APNs push notifications, Twilio/Gupshup SMS, WhatsApp messages, SendGrid/SES emails.
   - `queue:billing-jobs`: Batch generation of invoices, recurring dues, and automated interest/penalty sweeps.
   - `queue:reporting`: Generation of large monthly PDF balance sheets, gate security audits, and Excel dumps.
   - `queue:maintenance`: Housekeeping tasks, gate pass expiration sweeps, cache warmers.
3. **Resilience & Fault Tolerance**:
   - Exponential backoff retry policies (3 to 5 attempts) on external communication providers.
   - Dead-Letter Queues (DLQ) for failed jobs with alert notifications to administrators.
   - Job Idempotency: All jobs enforce unique deduplication keys based on `{society_id}:{job_type}:{timestamp_or_resource_id}` to prevent duplicate billings or duplicate SMS sends.

## Consequences
### Positive
- Sub-millisecond API response times for end users.
- Guaranteed delivery and retry semantics for critical SMS/WhatsApp emergency alerts and gate approvals.
- Isolated scaling: worker pods can be scaled independently of HTTP web pods.

### Negative / Trade-offs
- Requires Redis as a mandatory infrastructure dependency.
