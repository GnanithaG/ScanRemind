from datetime import UTC, datetime

from scanremind.db import STATUS_FAILED, STATUS_PENDING, STATUS_SENT, connect
from scanremind.delivery import next_occurrence, process_due_reminders

NOW = datetime(2030, 3, 1, 12, 0, tzinfo=UTC)


def insert(app, when="2030-03-01 11:59", repeat="none", tz="UTC"):
    conn = connect(app.config["DATABASE"])
    cur = conn.execute(
        "INSERT INTO reminders (username, email, title, description, reminder_datetime,"
        " repeat, timezone) VALUES ('Asha', 'a@example.com', 'Call mom', 'Sunday call', ?, ?, ?)",
        (when, repeat, tz),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def get(app, reminder_id):
    conn = connect(app.config["DATABASE"])
    row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
    conn.close()
    return row


def test_one_time_reminder_is_sent_once(app, mailer):
    rid = insert(app)
    assert process_due_reminders(app, NOW) == 1
    assert process_due_reminders(app, NOW) == 0
    assert get(app, rid)["sent"] == STATUS_SENT
    assert len(mailer.sent) == 1
    assert mailer.sent[0]["subject"] == "Reminder: Call mom"
    assert "Sunday call" in mailer.sent[0]["body"]


def test_future_reminder_is_not_sent(app, mailer):
    insert(app, when="2030-03-01 12:01")
    assert process_due_reminders(app, NOW) == 0
    assert mailer.sent == []


def test_daily_reminder_moves_to_next_day(app):
    rid = insert(app, repeat="daily")
    process_due_reminders(app, NOW)
    row = get(app, rid)
    assert row["sent"] == STATUS_PENDING
    assert row["reminder_datetime"] == "2030-03-02 11:59"


def test_missed_repeats_send_one_catch_up_email(app, mailer):
    # Server was down for 10 days: send once, then schedule the next future slot.
    rid = insert(app, when="2030-02-19 09:00", repeat="daily")
    process_due_reminders(app, NOW)
    assert len(mailer.sent) == 1
    assert get(app, rid)["reminder_datetime"] == "2030-03-02 09:00"


def test_failed_send_backs_off_then_gives_up(app, mailer):
    mailer.fail = True
    rid = insert(app)
    process_due_reminders(app, NOW)
    row = get(app, rid)
    assert row["attempts"] == 1
    assert row["next_attempt_at"] == "2030-03-01 12:02"
    assert "mail server down" in row["last_error"]

    # Not retried before the backoff time.
    process_due_reminders(app, NOW)
    assert get(app, rid)["attempts"] == 1

    for day in range(2, 2 + app.config["REMINDER_MAX_ATTEMPTS"]):
        process_due_reminders(app, datetime(2030, 3, day, tzinfo=UTC))
    row = get(app, rid)
    assert row["sent"] == STATUS_FAILED
    assert row["attempts"] == app.config["REMINDER_MAX_ATTEMPTS"]


def test_daily_repeat_keeps_local_time_across_dst():
    # 9:00 in Los Angeles is 17:00 UTC in winter and 16:00 UTC after DST starts.
    before = datetime(2030, 3, 9, 17, 0, tzinfo=UTC)
    after = next_occurrence(before, "daily", "America/Los_Angeles", before)
    assert after == datetime(2030, 3, 10, 16, 0, tzinfo=UTC)


def test_monthly_repeat_clamps_to_month_end():
    jan31 = datetime(2030, 1, 31, 9, 0, tzinfo=UTC)
    assert next_occurrence(jan31, "monthly", "UTC", jan31).day == 28
