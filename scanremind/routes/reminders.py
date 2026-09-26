import re
from datetime import datetime, timedelta

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

from ..db import STATUS_FAILED, STATUS_PENDING, STATUS_SENT, get_db
from ..delivery import REPEAT_OPTIONS, format_utc, get_zone, parse_utc, utcnow
from ..mailer import mask_email

reminders_bp = Blueprint("reminders", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STATUS_LABELS = {STATUS_PENDING: "Scheduled", STATUS_SENT: "Sent", STATUS_FAILED: "Failed"}


def normalize_email(value: str) -> str:
    return value.strip().lower()


def validate_reminder_form(form) -> tuple[dict, list[str]]:
    """Return (clean data, errors) for the create-reminder form."""
    cfg = current_app.config
    errors = []
    data = {
        "username": form.get("username", "").strip(),
        "email": normalize_email(form.get("email", "")),
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "repeat": form.get("repeat", "none"),
        "timezone": form.get("timezone") or "UTC",
    }

    for field, label, limit in (
        ("username", "Your name", cfg["MAX_NAME_LENGTH"]),
        ("title", "Title", cfg["MAX_TITLE_LENGTH"]),
        ("description", "Description", cfg["MAX_DESCRIPTION_LENGTH"]),
    ):
        if not data[field]:
            errors.append(f"{label} is required.")
        elif len(data[field]) > limit:
            errors.append(f"{label} must be {limit} characters or fewer.")

    if not EMAIL_RE.match(data["email"]) or len(data["email"]) > 254:
        errors.append("Please enter a valid email address.")

    if data["repeat"] not in REPEAT_OPTIONS:
        errors.append("Please choose a valid repeat option.")

    zone = get_zone(data["timezone"])
    data["timezone"] = zone.key
    try:
        local = datetime.strptime(
            f"{form.get('reminder_date', '')} {form.get('reminder_time', '')}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        errors.append("Please enter a valid date and time.")
    else:
        when = local.replace(tzinfo=zone)
        if when < utcnow() + timedelta(minutes=1):
            errors.append("Please pick a time at least 1 minute from now.")
        data["reminder_datetime"] = format_utc(when)

    return data, errors


@reminders_bp.route("/set-reminder")
def set_reminder():
    return render_template("index.html", form={})


@reminders_bp.route("/create-reminder", methods=["POST"])
def create_reminder():
    data, errors = validate_reminder_form(request.form)
    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("index.html", form=request.form), 400

    db = get_db()
    db.execute(
        """
        INSERT INTO reminders
            (username, email, title, description, reminder_datetime, repeat, timezone, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["username"],
            data["email"],
            data["title"],
            data["description"],
            data["reminder_datetime"],
            data["repeat"],
            data["timezone"],
            format_utc(utcnow()),
        ),
    )
    db.commit()
    current_app.logger.info(
        "Reminder created for %s at %s UTC", mask_email(data["email"]), data["reminder_datetime"]
    )
    local = parse_utc(data["reminder_datetime"]).astimezone(get_zone(data["timezone"]))
    return render_template("success.html", username=data["username"], when=local)


@reminders_bp.route("/my-reminders")
def my_reminders():
    email = session.get("verified_email")
    if not email:
        flash("Please verify your email to see your reminders.", "error")
        return redirect(url_for("auth.manage_reminders"))

    rows = (
        get_db()
        .execute(
            """
        SELECT id, title, description, reminder_datetime, repeat, sent, timezone
        FROM reminders WHERE email = ?
        ORDER BY sent, reminder_datetime
        """,
            (email,),
        )
        .fetchall()
    )

    reminders = [
        {
            "id": row["id"],
            "title": row["title"],
            "description": row["description"],
            "repeat": row["repeat"],
            "status": STATUS_LABELS.get(row["sent"], "Scheduled"),
            "status_class": {STATUS_SENT: "sent", STATUS_FAILED: "failed"}.get(
                row["sent"], "pending"
            ),
            "when": parse_utc(row["reminder_datetime"]).astimezone(get_zone(row["timezone"])),
            "timezone": row["timezone"],
        }
        for row in rows
    ]
    return render_template("my_reminders.html", reminders=reminders, email=email)


@reminders_bp.route("/delete-reminder/<int:reminder_id>", methods=["POST"])
def delete_reminder(reminder_id: int):
    email = session.get("verified_email")
    if not email:
        flash("Please verify your email to manage your reminders.", "error")
        return redirect(url_for("auth.manage_reminders"))

    db = get_db()
    # Only delete the reminder if it belongs to the verified email.
    deleted = db.execute(
        "DELETE FROM reminders WHERE id = ? AND email = ?", (reminder_id, email)
    ).rowcount
    db.commit()

    if deleted:
        flash("Reminder deleted.", "success")
    else:
        flash("That reminder doesn't exist.", "error")
    return redirect(url_for("reminders.my_reminders"))
