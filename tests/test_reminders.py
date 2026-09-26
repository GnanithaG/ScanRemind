from datetime import UTC, datetime, timedelta

from conftest import login

from scanremind.db import connect


def future(days=1, tz=UTC):
    when = datetime.now(tz) + timedelta(days=days)
    return when.strftime("%Y-%m-%d"), when.strftime("%H:%M")


def reminder_form(**overrides):
    date, time = future()
    form = {
        "username": "Asha",
        "email": "Asha@Example.com",
        "title": "Water the plants",
        "description": "Both balconies",
        "reminder_date": date,
        "reminder_time": time,
        "repeat": "none",
        "timezone": "UTC",
    }
    form.update(overrides)
    return form


def rows(app, sql="SELECT * FROM reminders", params=()):
    conn = connect(app.config["DATABASE"])
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def add_reminder(app, email="owner@example.com", title="Owned"):
    conn = connect(app.config["DATABASE"])
    cur = conn.execute(
        "INSERT INTO reminders (username, email, title, description, reminder_datetime)"
        " VALUES ('x', ?, ?, 'd', '2030-01-01 09:00')",
        (email, title),
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def test_create_reminder_stores_utc_and_normalised_email(client, app):
    response = client.post(
        "/create-reminder",
        data=reminder_form(
            timezone="America/Los_Angeles",
            reminder_date="2030-07-01",
            reminder_time="09:00",
        ),
    )
    assert response.status_code == 200
    assert b"Reminder scheduled" in response.data

    [row] = rows(app)
    assert row["email"] == "asha@example.com"
    assert row["reminder_datetime"] == "2030-07-01 16:00"  # 9:00 PDT = 16:00 UTC
    assert row["timezone"] == "America/Los_Angeles"


def test_past_time_is_rejected(client, app):
    response = client.post(
        "/create-reminder",
        data=reminder_form(
            reminder_date="2020-01-01",
            reminder_time="09:00",
        ),
    )
    assert response.status_code == 400
    assert b"at least 1 minute from now" in response.data
    assert rows(app) == []


def test_invalid_input_is_rejected_and_form_is_kept(client, app):
    response = client.post(
        "/create-reminder",
        data=reminder_form(
            repeat="hourly",
            email="not-an-email",
            title="x" * 500,
        ),
    )
    assert response.status_code == 400
    assert b"valid repeat option" in response.data
    assert b"valid email" in response.data
    assert b"120 characters or fewer" in response.data
    assert b'value="Asha"' in response.data  # the user's input is preserved
    assert rows(app) == []


def test_bad_date_does_not_crash(client):
    response = client.post("/create-reminder", data=reminder_form(reminder_date="soon"))
    assert response.status_code == 400
    assert b"valid date and time" in response.data


def test_unknown_timezone_falls_back_to_utc(client, app):
    client.post("/create-reminder", data=reminder_form(timezone="Mars/Olympus"))
    assert rows(app)[0]["timezone"] == "UTC"


def test_my_reminders_requires_verification(client):
    response = client.get("/my-reminders")
    assert response.status_code == 302
    assert "/manage-reminders" in response.headers["Location"]


def test_my_reminders_only_shows_own(client, app):
    add_reminder(app, "me@example.com", "Mine")
    add_reminder(app, "other@example.com", "Theirs")
    login(client, "me@example.com")
    page = client.get("/my-reminders").data
    assert b"Mine" in page
    assert b"Theirs" not in page


def test_cannot_delete_someone_elses_reminder(client, app):
    victim = add_reminder(app, "victim@example.com")
    login(client, "attacker@example.com")
    client.post(f"/delete-reminder/{victim}")
    assert len(rows(app)) == 1


def test_delete_requires_verification(client, app):
    reminder = add_reminder(app)
    client.post(f"/delete-reminder/{reminder}")
    assert len(rows(app)) == 1


def test_owner_can_delete(client, app):
    reminder = add_reminder(app, "owner@example.com")
    login(client, "owner@example.com")
    response = client.post(f"/delete-reminder/{reminder}", follow_redirects=True)
    assert b"Reminder deleted" in response.data
    assert rows(app) == []
