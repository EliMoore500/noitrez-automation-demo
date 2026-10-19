import json
import os
import re
import time
from collections import defaultdict, deque
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
CONTACT_RATE_LIMIT = 5
CONTACT_RATE_WINDOW = 15 * 60
contact_requests = defaultdict(deque)


def allowed_contact_origins():
    configured = os.getenv("CONTACT_ALLOWED_ORIGINS", "").strip()
    if configured:
        return {origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()}
    return {
        "https://noitrez.com",
        "https://www.noitrez.com",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    }


@app.after_request
def add_contact_cors_headers(response):
    origin = request.headers.get("Origin", "").rstrip("/")
    if request.path == "/api/contact" and origin in allowed_contact_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Max-Age"] = "600"
        response.headers["Vary"] = "Origin"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.errorhandler(413)
def handle_large_request(_error):
    return jsonify({"error": "The request is too large."}), 413


@app.errorhandler(500)
def handle_server_error(error):
    if request.path.startswith("/api/"):
        app.logger.exception("Unhandled API error", exc_info=error)
        return jsonify({"error": "The server could not complete this request."}), 500
    return error


def email_settings():
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("RESEND_FROM", "").strip()
    recipient = os.getenv(
        "CONTACT_NOTIFICATION_EMAIL",
        os.getenv("BUSINESS_NOTIFICATION_EMAIL", "sales@noitrez.com"),
    ).strip()

    if not all([api_key, sender, recipient]):
        return None, "Resend API key or verified sender is not configured."

    return {
        "api_key": api_key,
        "sender": sender,
        "recipient": recipient,
    }, ""


def send_email(message, settings):
    payload = {
        "from": settings["sender"],
        "to": [settings["recipient"]],
        "subject": str(message["Subject"]),
        "text": message.get_content(),
        "reply_to": str(message["Reply-To"]),
    }
    request = Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            response.read()
    except HTTPError as error:
        app.logger.error("Resend rejected contact email with HTTP %s", error.code)
        return False, "Email provider rejected the message."
    except (OSError, URLError):
        app.logger.exception("Resend contact email request failed")
        return False, "Email provider could not be reached."

    return True, "Email sent successfully."


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/contact", methods=["POST", "OPTIONS"])
def submit_contact_request():
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin not in allowed_contact_origins():
        return jsonify({"error": "This origin is not allowed."}), 403
    if request.method == "OPTIONS":
        return ("", 204)
    if not request.is_json:
        return jsonify({"error": "Submit the contact form as JSON."}), 400

    data = request.get_json(silent=True) or {}
    if str(data.get("website", "")).strip():
        return jsonify({"success": True, "message": "Request received."})

    fields = {
        "name": str(data.get("name", "")).strip(),
        "email": str(data.get("email", "")).strip(),
        "business": str(data.get("business", "")).strip(),
        "request": str(data.get("request", "")).strip(),
    }
    required = ("name", "email", "request")
    missing = [field for field in required if not fields[field]]
    if missing:
        return jsonify({"error": "Please complete your name, email, and request."}), 400
    limits = {"name": 120, "email": 254, "business": 160, "request": 3000}
    if any(len(fields[field]) > limit for field, limit in limits.items()):
        return jsonify({"error": "One or more fields are too long."}), 400
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", fields["email"]):
        return jsonify({"error": "Please provide a valid email address."}), 400

    now = time.monotonic()
    client_ip = request.remote_addr or "unknown"
    attempts = contact_requests[client_ip]
    while attempts and now - attempts[0] > CONTACT_RATE_WINDOW:
        attempts.popleft()
    if len(attempts) >= CONTACT_RATE_LIMIT:
        return jsonify({"error": "Too many requests. Please try again later."}), 429
    attempts.append(now)

    settings, _status = email_settings()
    if settings is None:
        return jsonify({
            "error": "The contact service is temporarily unavailable. Please email sales@noitrez.com.",
        }), 503

    message = EmailMessage()
    message["Subject"] = "Free Automation Audit Request"
    message["From"] = settings["sender"]
    message["To"] = settings["recipient"]
    message["Reply-To"] = fields["email"]
    message.set_content(
        "A new website audit request was submitted.\n\n"
        f"Name: {fields['name']}\n"
        f"Email: {fields['email']}\n"
        f"Business: {fields['business'] or 'Not provided'}\n\n"
        f"What they would like to automate:\n{fields['request']}\n"
    )
    sent, _email_status = send_email(message, settings)
    if not sent:
        return jsonify({
            "error": "We couldn't send your request just now. Please email sales@noitrez.com.",
        }), 502
    return jsonify({"success": True, "message": "Your request has been sent to Noitrez."})


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
