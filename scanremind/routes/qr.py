import io
from functools import lru_cache

import qrcode
from flask import Blueprint, current_app, render_template, send_file, url_for

qr_bp = Blueprint("qr", __name__)


@lru_cache(maxsize=8)
def _qr_png(url: str) -> bytes:
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def target_url() -> str:
    """Where the QR code sends people: APP_URL, or this site's reminder form."""
    return current_app.config.get("APP_URL") or url_for("reminders.set_reminder", _external=True)


@qr_bp.route("/")
def qr_code_page():
    return render_template("qrcode.html", target_url=target_url())


@qr_bp.route("/qr-code")
def generate_qr():
    response = send_file(io.BytesIO(_qr_png(target_url())), mimetype="image/png")
    response.cache_control.max_age = 3600
    return response
