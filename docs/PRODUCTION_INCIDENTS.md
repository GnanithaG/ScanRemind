# Production Incidents Log

## Deployment: June 6, 2026 — Initial Production Launch

---

### INC-001: Database Tables Not Found on Startup
**Error:** `sqlite3.OperationalError: no such table: otp_store`

**Cause:** `init_db()` was called inside `if __name__ == '__main__'` which does not execute when the app is launched via gunicorn. Tables were never created on the production server.

**Fix:** Moved `init_db()` inside `create_app()` so it runs on every startup regardless of how the app is launched.

---

### INC-002: Gmail SMTP Worker Timeout
**Error:** `WORKER TIMEOUT` on `/send-otp`

**Cause:** Google actively blocks or throttles SMTP connections originating from known cloud datacenter IP ranges to prevent spam. Local SMTP worked fine but failed in production.

**Fix:** Replaced Flask-Mail with Resend for transactional email delivery.

---

### INC-003: Resend Email Restriction
**Error:** `You can only send testing emails to your own email address`

**Cause:** Resend's free tier restricts outbound email to the account owner's verified email address until a custom domain is verified.

**Status:** Resolved. Switched to Brevo's transactional email API, which can send to any address from a verified sender. Since v2.0 the Brevo API is called directly with a 10-second timeout so a slow provider can't hang a worker.

---

### INC-004: Multiple Scheduler Instances
**Symptom:** 4-5 emails delivered per reminder instead of one.

**Cause:** Gunicorn spawns multiple worker processes. Each worker called `create_app()` which started its own `BackgroundScheduler` instance. All schedulers fired simultaneously for every due reminder.

**Fix:** Removed scheduler from `create_app()`. Moved it to a gunicorn server hook in `gunicorn_config.py` using `on_starting()` — ensures exactly one scheduler instance starts at the server level regardless of worker count.

**Update (v2.0):** The hook now lives in `gunicorn.conf.py`. The scheduled job no longer builds a new Flask app on every run (which also stacked up a new log handler each minute), and `max_instances=1` stops two checks from overlapping.

---

### INC-005: Timezone Mismatch on Datetime Validation
**Symptom:** Future datetime validation rejecting valid future times submitted from the browser.

**Cause:** Production server runs on UTC. Users submit local time without timezone context. A reminder set for 9:00 PM EST was interpreted as already past by the UTC server.

**Fix:** Added browser-side timezone detection using `Intl.DateTimeFormat().resolvedOptions().timeZone`. Submitted datetime is converted from user's local timezone to UTC before storage and comparison using `pytz`.

---

### INC-006: Infinite Reminder Retry on Email Failure
**Symptom:** Scheduler retried the same failed reminder every minute indefinitely.

**Cause:** When email delivery fails, the reminder stays `sent=0` in the database. The scheduler has no retry limit so it keeps attempting delivery on every interval.

**Status:** Resolved in v2.0. Failed sends are retried after 2, 4, 8 and 16 minutes, then marked *Failed* after 5 attempts. The error is stored on the reminder for debugging. Covered by `tests/test_delivery.py`.
