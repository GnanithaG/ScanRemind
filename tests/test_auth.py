import re

from conftest import login

from scanremind.db import connect


def request_code(client, mailer, email="me@example.com"):
    response = client.post("/send-otp", data={"email": email})
    code = re.search(r"\b(\d{6})\b", mailer.sent[-1]["body"]).group(1)
    return response, code


def test_code_is_sent_and_stored_hashed(client, app, mailer):
    response, code = request_code(client, mailer)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify-otp")
    assert mailer.sent[-1]["to"] == "me@example.com"

    conn = connect(app.config["DATABASE"])
    [row] = conn.execute("SELECT * FROM otp_codes").fetchall()
    conn.close()
    assert code not in row["code_hash"]


def test_correct_code_signs_in(client, mailer):
    _, code = request_code(client, mailer)
    response = client.post("/verify-otp", data={"otp": code})
    assert response.headers["Location"].endswith("/my-reminders")
    with client.session_transaction() as session:
        assert session["verified_email"] == "me@example.com"


def test_code_cannot_be_reused(client, mailer):
    _, code = request_code(client, mailer)
    client.post("/verify-otp", data={"otp": code})
    with client.session_transaction() as session:
        session.clear()
        session["otp_email"] = "me@example.com"
    response = client.post("/verify-otp", data={"otp": code})
    assert "/manage-reminders" in response.headers["Location"]


def test_wrong_code_is_rejected(client, mailer):
    request_code(client, mailer)
    response = client.post("/verify-otp", data={"otp": "000000"})
    assert response.status_code == 400
    with client.session_transaction() as session:
        assert "verified_email" not in session


def test_code_locks_after_too_many_attempts(client, app, mailer):
    _, code = request_code(client, mailer)
    wrong = "111111" if code != "111111" else "222222"
    for _ in range(app.config["OTP_MAX_ATTEMPTS"]):
        client.post("/verify-otp", data={"otp": wrong})
    # Even the right code no longer works once the code is locked.
    response = client.post("/verify-otp", data={"otp": code})
    assert "/manage-reminders" in response.headers["Location"]
    with client.session_transaction() as session:
        assert "verified_email" not in session


def test_expired_code_is_rejected(client, app, mailer):
    _, code = request_code(client, mailer)
    conn = connect(app.config["DATABASE"])
    conn.execute("UPDATE otp_codes SET expires_at = '2000-01-01 00:00'")
    conn.commit()
    conn.close()
    response = client.post("/verify-otp", data={"otp": code})
    assert "/manage-reminders" in response.headers["Location"]


def test_code_requests_are_rate_limited(client, app, mailer):
    for _ in range(app.config["OTP_MAX_REQUESTS"]):
        client.post("/send-otp", data={"email": "me@example.com"})
    response = client.post("/send-otp", data={"email": "me@example.com"}, follow_redirects=True)
    assert b"Too many codes requested" in response.data
    assert len(mailer.sent) == app.config["OTP_MAX_REQUESTS"]


def test_mail_failure_shows_error(client, mailer):
    mailer.fail = True
    response = client.post("/send-otp", data={"email": "me@example.com"}, follow_redirects=True)
    assert b"couldn&#39;t send the code" in response.data


def test_logout_clears_session(client):
    login(client, "me@example.com")
    client.post("/logout")
    with client.session_transaction() as session:
        assert "verified_email" not in session
