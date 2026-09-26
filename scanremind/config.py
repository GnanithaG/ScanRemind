"""Application configuration, read from environment variables.

Every setting can be overridden with an environment variable of the same
name (see `.env.example`). Tests pass overrides directly to `create_app`.
"""

import os
from datetime import timedelta


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> dict:
    debug = _env_bool("FLASK_DEBUG", False)
    return {
        "DEBUG": debug,
        "SECRET_KEY": os.getenv("FLASK_SECRET_KEY"),
        "DATABASE": os.getenv("DATABASE_PATH", "reminders.db"),
        # Public URL the QR code points to. `URL` is kept for older deployments.
        "APP_URL": os.getenv("APP_URL") or os.getenv("URL"),
        # "brevo" sends real email; "console" only logs it (handy locally).
        "MAIL_BACKEND": os.getenv("MAIL_BACKEND", "console" if debug else "brevo"),
        "BREVO_API_KEY": os.getenv("BREVO_API_KEY"),
        "MAIL_SENDER_EMAIL": os.getenv("MAIL_SENDER_EMAIL") or os.getenv("BREVO_SENDER_EMAIL"),
        "MAIL_SENDER_NAME": os.getenv("MAIL_SENDER_NAME", "ScanRemind"),
        # Sessions
        "PERMANENT_SESSION_LIFETIME": timedelta(minutes=10),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": _env_bool("SESSION_COOKIE_SECURE", not debug),
        # One-time passwords
        "OTP_TTL_MINUTES": 10,
        "OTP_MAX_ATTEMPTS": 5,
        "OTP_MAX_REQUESTS": 3,  # per email address...
        "OTP_REQUEST_WINDOW_MINUTES": 10,  # ...within this window
        # Reminder delivery
        "REMINDER_MAX_ATTEMPTS": 5,
        "SCHEDULER_INTERVAL_SECONDS": 60,
        # Form limits
        "MAX_TITLE_LENGTH": 120,
        "MAX_DESCRIPTION_LENGTH": 2000,
        "MAX_NAME_LENGTH": 80,
    }
