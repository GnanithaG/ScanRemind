"""Finding due reminders and delivering them.

All reminder times are stored in UTC. Repeating reminders are advanced in
the user's own time zone so a "9:00 every day" reminder stays at 9:00 local
time across daylight-saving changes.
"""

import logging
from contextlib import closing
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.relativedelta import relativedelta

from .db import STATUS_FAILED, STATUS_PENDING, STATUS_SENT, connect
from .mailer import mask_email, send_email

log = logging.getLogger(__name__)

DATETIME_FMT = "%Y-%m-%d %H:%M"
REPEAT_STEPS = {
    "daily": relativedelta(days=1),
    "weekly": relativedelta(weeks=1),
    "monthly": relativedelta(months=1),
}
REPEAT_OPTIONS = ("none", *REPEAT_STEPS)


def utcnow() -> datetime:
    return datetime.now(UTC)


def format_utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(DATETIME_FMT)


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, DATETIME_FMT).replace(tzinfo=UTC)


def get_zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def next_occurrence(current: datetime, repeat: str, tz_name: str, now: datetime) -> datetime:
    """The first occurrence after `now`, stepping in the user's local time.

    Skipping every missed occurrence means a server that was down for a
    while sends one catch-up email instead of one per missed interval.
    """
    step = REPEAT_STEPS[repeat]
    zone = get_zone(tz_name)
    local = current.astimezone(zone).replace(tzinfo=None)  # wall-clock time
    while True:
        local += step
        candidate = local.replace(tzinfo=zone).astimezone(UTC)
        if candidate > now:
            return candidate


def reminder_email(row) -> tuple[str, str]:
    subject = f"Reminder: {row['title']}"
    body = (
        f"Hello {row['username']},\n\n"
        f"This is your ScanRemind reminder.\n\n"
        f"{row['title']}\n\n"
        f"{row['description']}\n\n"
        f"Manage your reminders any time from the ScanRemind page.\n\n"
        f"ScanRemind"
    )
    return subject, body


def process_due_reminders(app, now: datetime | None = None) -> int:
    """Send every reminder that is due. Returns the number sent."""
    now = now or utcnow()
    now_str = format_utc(now)
    max_attempts = app.config["REMINDER_MAX_ATTEMPTS"]
    sent_count = 0

    with closing(connect(app.config["DATABASE"])) as conn:
        due = conn.execute(
            """
            SELECT * FROM reminders
            WHERE sent = ? AND reminder_datetime <= ?
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY reminder_datetime
            """,
            (STATUS_PENDING, now_str, now_str),
        ).fetchall()

        for row in due:
            subject, body = reminder_email(row)
            try:
                send_email(app, row["email"], subject, body)
            except Exception as exc:  # noqa: BLE001 - any failure is retried
                attempts = row["attempts"] + 1
                if attempts >= max_attempts:
                    conn.execute(
                        "UPDATE reminders SET attempts = ?, sent = ?, last_error = ?,"
                        " next_attempt_at = NULL WHERE id = ?",
                        (attempts, STATUS_FAILED, str(exc)[:500], row["id"]),
                    )
                    log.error(
                        "Giving up on reminder %s after %s attempts: %s", row["id"], attempts, exc
                    )
                else:
                    retry_at = now + timedelta(minutes=2**attempts)  # 2, 4, 8, 16 min
                    conn.execute(
                        "UPDATE reminders SET attempts = ?, last_error = ?,"
                        " next_attempt_at = ? WHERE id = ?",
                        (attempts, str(exc)[:500], format_utc(retry_at), row["id"]),
                    )
                    log.warning(
                        "Reminder %s failed (attempt %s), retrying at %s: %s",
                        row["id"],
                        attempts,
                        format_utc(retry_at),
                        exc,
                    )
                conn.commit()
                continue

            if row["repeat"] in REPEAT_STEPS:
                upcoming = next_occurrence(
                    parse_utc(row["reminder_datetime"]), row["repeat"], row["timezone"], now
                )
                conn.execute(
                    "UPDATE reminders SET reminder_datetime = ?, attempts = 0,"
                    " next_attempt_at = NULL, last_error = NULL WHERE id = ?",
                    (format_utc(upcoming), row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE reminders SET sent = ?, next_attempt_at = NULL, last_error = NULL"
                    " WHERE id = ?",
                    (STATUS_SENT, row["id"]),
                )
            conn.commit()
            sent_count += 1
            log.info(
                "Sent reminder %s to %s (repeat: %s)",
                row["id"],
                mask_email(row["email"]),
                row["repeat"],
            )

        # Housekeeping: drop one-time codes older than a day.
        conn.execute(
            "DELETE FROM otp_codes WHERE created_at < ?", (format_utc(now - timedelta(days=1)),)
        )
        conn.commit()

    return sent_count
