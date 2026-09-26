"""Outgoing email.

The production backend calls Brevo's transactional email REST API directly.
The console backend only logs messages, so the app runs locally without an
email account.
"""

import logging

import requests

BREVO_URL = "https://api.brevo.com/v3/smtp/email"

log = logging.getLogger(__name__)


class MailError(Exception):
    pass


def mask_email(email: str) -> str:
    """'jane.doe@example.com' -> 'ja***@example.com', for logs."""
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"


class ConsoleMailer:
    def send(self, to: str, subject: str, body: str) -> None:
        log.info("Email to %s | %s\n%s", to, subject, body)


class BrevoMailer:
    def __init__(self, api_key: str, sender_email: str, sender_name: str, timeout: float = 10):
        self.api_key = api_key
        self.sender = {"email": sender_email, "name": sender_name}
        self.timeout = timeout

    def send(self, to: str, subject: str, body: str) -> None:
        try:
            response = requests.post(
                BREVO_URL,
                headers={"api-key": self.api_key, "accept": "application/json"},
                json={
                    "sender": self.sender,
                    "to": [{"email": to}],
                    "subject": subject,
                    "textContent": body,
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise MailError(f"Could not reach Brevo: {exc}") from exc
        if response.status_code >= 400:
            raise MailError(f"Brevo returned {response.status_code}: {response.text[:200]}")


def init_app(app) -> None:
    backend = app.config["MAIL_BACKEND"]
    if backend == "console":
        mailer = ConsoleMailer()
    elif backend == "brevo":
        missing = [k for k in ("BREVO_API_KEY", "MAIL_SENDER_EMAIL") if not app.config.get(k)]
        if missing:
            raise RuntimeError(
                f"MAIL_BACKEND=brevo needs {', '.join(missing)}. "
                "Set them in .env, or use MAIL_BACKEND=console for local development."
            )
        mailer = BrevoMailer(
            app.config["BREVO_API_KEY"],
            app.config["MAIL_SENDER_EMAIL"],
            app.config["MAIL_SENDER_NAME"],
        )
    else:
        raise RuntimeError(f"Unknown MAIL_BACKEND {backend!r} (use 'brevo' or 'console')")
    app.extensions["mailer"] = mailer


def send_email(app, to: str, subject: str, body: str) -> None:
    app.extensions["mailer"].send(to, subject, body)
