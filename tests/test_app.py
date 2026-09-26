import sqlite3

import pytest

from scanremind import create_app
from scanremind.db import init_db


def test_landing_page_and_qr_code(client):
    page = client.get("/")
    assert page.status_code == 200
    assert b"https://scanremind.example/set-reminder" in page.data

    qr = client.get("/qr-code")
    assert qr.status_code == 200
    assert qr.mimetype == "image/png"
    assert qr.data.startswith(b"\x89PNG")


def test_reminder_form_renders(client):
    response = client.get("/set-reminder")
    assert response.status_code == 200
    assert b"Create a reminder" in response.data


def test_unknown_page_is_404(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert b"Page not found" in response.data


def test_csrf_is_enforced(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "x",
            "MAIL_BACKEND": "console",
            "DATABASE": str(tmp_path / "db.sqlite"),
        }
    )
    response = app.test_client().post("/send-otp", data={"email": "me@example.com"})
    assert response.status_code == 400
    assert b"Form expired" in response.data


def test_missing_secret_key_fails_fast(tmp_path, monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        create_app(
            {"SECRET_KEY": None, "MAIL_BACKEND": "console", "DATABASE": str(tmp_path / "db.sqlite")}
        )


def test_brevo_backend_requires_credentials(tmp_path):
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        create_app(
            {
                "SECRET_KEY": "x",
                "MAIL_BACKEND": "brevo",
                "BREVO_API_KEY": None,
                "DATABASE": str(tmp_path / "db.sqlite"),
            }
        )


def test_old_database_is_upgraded_in_place(tmp_path):
    """A database created by the original version keeps its data."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,"
        " email TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,"
        " reminder_datetime TEXT NOT NULL, repeat TEXT DEFAULT 'none', sent INTEGER DEFAULT 0)"
    )
    conn.execute(
        "INSERT INTO reminders (username, email, title, description, reminder_datetime)"
        " VALUES ('a', 'a@example.com', 't', 'd', '2030-01-01 09:00')"
    )
    conn.commit()
    conn.close()

    init_db(str(path))

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM reminders").fetchone()
    conn.close()
    assert row["title"] == "t"
    assert row["timezone"] == "UTC"
    assert row["attempts"] == 0
