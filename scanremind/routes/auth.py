import hashlib
import hmac
import secrets
from datetime import timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..db import get_db
from ..delivery import format_utc, utcnow
from ..mailer import mask_email, send_email
from .reminders import EMAIL_RE, normalize_email

auth_bp = Blueprint("auth", __name__)


def hash_code(email: str, code: str) -> str:
    """Codes are stored as keyed hashes, never in plain text."""
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


@auth_bp.route("/manage-reminders")
def manage_reminders():
    if session.get("verified_email"):
        return redirect(url_for("reminders.my_reminders"))
    return render_template("manage_reminders.html")


@auth_bp.route("/send-otp", methods=["POST"])
def send_otp():
    cfg = current_app.config
    email = normalize_email(request.form.get("email", ""))
    if not EMAIL_RE.match(email):
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("auth.manage_reminders"))

    db = get_db()
    now = utcnow()
    window_start = format_utc(now - timedelta(minutes=cfg["OTP_REQUEST_WINDOW_MINUTES"]))
    recent = db.execute(
        "SELECT COUNT(*) FROM otp_codes WHERE email = ? AND created_at >= ?",
        (email, window_start),
    ).fetchone()[0]
    if recent >= cfg["OTP_MAX_REQUESTS"]:
        flash("Too many codes requested. Please wait a few minutes and try again.", "error")
        return redirect(url_for("auth.manage_reminders"))

    code = f"{secrets.randbelow(1_000_000):06d}"
    # A new code replaces any earlier unused one.
    db.execute("UPDATE otp_codes SET used = 1 WHERE email = ? AND used = 0", (email,))
    db.execute(
        "INSERT INTO otp_codes (email, code_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (
            email,
            hash_code(email, code),
            format_utc(now),
            format_utc(now + timedelta(minutes=cfg["OTP_TTL_MINUTES"])),
        ),
    )
    db.commit()

    try:
        send_email(
            current_app._get_current_object(),
            email,
            "Your ScanRemind verification code",
            f"Your ScanRemind verification code is {code}.\n\n"
            f"It expires in {cfg['OTP_TTL_MINUTES']} minutes. Don't share it with anyone.",
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.error("Could not send code to %s: %s", mask_email(email), exc)
        flash("We couldn't send the code. Please try again.", "error")
        return redirect(url_for("auth.manage_reminders"))

    session["otp_email"] = email
    return redirect(url_for("auth.verify_otp"))


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    email = session.get("otp_email")
    if not email:
        return redirect(url_for("auth.manage_reminders"))
    if request.method == "GET":
        return render_template("verify_otp.html", email=email)

    db = get_db()
    row = db.execute(
        "SELECT id, code_hash, expires_at, attempts FROM otp_codes"
        " WHERE email = ? AND used = 0 ORDER BY id DESC LIMIT 1",
        (email,),
    ).fetchone()

    if not row or row["expires_at"] < format_utc(utcnow()):
        flash("That code has expired. Please request a new one.", "error")
        return redirect(url_for("auth.manage_reminders"))

    entered = request.form.get("otp", "").strip()
    if not hmac.compare_digest(hash_code(email, entered), row["code_hash"]):
        attempts = row["attempts"] + 1
        locked = attempts >= current_app.config["OTP_MAX_ATTEMPTS"]
        db.execute(
            "UPDATE otp_codes SET attempts = ?, used = ? WHERE id = ?",
            (attempts, int(locked), row["id"]),
        )
        db.commit()
        if locked:
            flash("Too many incorrect attempts. Please request a new code.", "error")
            return redirect(url_for("auth.manage_reminders"))
        flash("That code isn't right. Please try again.", "error")
        return render_template("verify_otp.html", email=email), 400

    db.execute("UPDATE otp_codes SET used = 1 WHERE id = ?", (row["id"],))
    db.commit()

    session.clear()  # fresh session after login
    session["verified_email"] = email
    session.permanent = True
    return redirect(url_for("reminders.my_reminders"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You've been signed out.", "success")
    return redirect(url_for("reminders.set_reminder"))
