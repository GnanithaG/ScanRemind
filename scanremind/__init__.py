"""ScanRemind: scan a QR code, set a reminder, get an email when it's due."""

import logging
import secrets

import click
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_wtf.csrf import CSRFError, CSRFProtect

from . import db, mailer
from .config import load_config

csrf = CSRFProtect()


def create_app(overrides: dict | None = None) -> Flask:
    load_dotenv()
    app = Flask(__name__)
    app.config.update(load_config())
    if overrides:
        app.config.update(overrides)

    if not app.config.get("SECRET_KEY"):
        if app.debug or app.testing:
            app.config["SECRET_KEY"] = secrets.token_hex(32)
        else:
            raise RuntimeError(
                "FLASK_SECRET_KEY is not set. Generate one with "
                '`python -c "import secrets; print(secrets.token_hex(32))"`.'
            )

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    db.init_app(app)
    mailer.init_app(app)
    csrf.init_app(app)

    from .routes.auth import auth_bp
    from .routes.qr import qr_bp
    from .routes.reminders import reminders_bp

    app.register_blueprint(qr_bp)
    app.register_blueprint(reminders_bp)
    app.register_blueprint(auth_bp)

    _register_error_pages(app)
    _register_commands(app)
    return app


def _register_error_pages(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def csrf_error(_e):
        return render_template(
            "error.html",
            title="Form expired",
            message="That form expired. Go back, refresh the page and try again.",
        ), 400

    @app.errorhandler(404)
    def not_found(_e):
        return render_template(
            "error.html",
            title="Page not found",
            message="We couldn't find that page.",
        ), 404

    @app.errorhandler(500)
    def server_error(_e):
        return render_template(
            "error.html",
            title="Something went wrong",
            message="Something went wrong on our side. Please try again in a moment.",
        ), 500


def _register_commands(app: Flask) -> None:
    @app.cli.command("send-due")
    def send_due():
        """Send due reminders once (for use from cron instead of the scheduler)."""
        from .delivery import process_due_reminders

        click.echo(f"Sent {process_due_reminders(app)} reminder(s).")
