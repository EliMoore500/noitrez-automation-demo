import os
import re
import smtplib
import time
from collections import defaultdict, deque
from email.message import EmailMessage

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


def smtp_settings():
    if os.getenv("SMTP_ENABLED", "false").lower() != "true":
        return None, "SMTP email is disabled. Lead was saved successfully."

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    sender = os.getenv("SMTP_FROM", username).strip()
    password = "".join(os.getenv("SMTP_PASSWORD", "").split())
    recipient = os.getenv(
        "CONTACT_NOTIFICATION_EMAIL",
        os.getenv("BUSINESS_NOTIFICATION_EMAIL", ""),
    ).strip()
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    if not all([host, username, sender, password, recipient]):
        return None, "SMTP is enabled but one or more SMTP settings are missing in .env"

    return {
        "host": host,
        "port": port,
        "username": username,
        "sender": sender,
        "password": password,
        "recipient": recipient,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
    }, ""


def send_email(message, settings):
    try:
        smtp_client = smtplib.SMTP_SSL if settings["use_ssl"] else smtplib.SMTP
        with smtp_client(settings["host"], settings["port"], timeout=20) as server:
            if settings["use_tls"] and not settings["use_ssl"]:
                server.starttls()
            server.login(settings["username"], settings["password"])
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        app.logger.exception("SMTP authentication failed")
        return False, (
            "SMTP authentication failed. The Gmail App Password must belong to "
            f"{settings['username']}. Generate a new App Password while signed "
            "into that exact Google account, then restart the Flask app."
        )
    except (OSError, smtplib.SMTPException) as exc:
        app.logger.exception("SMTP send failed")
        return False, f"SMTP send failed: {exc}"

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

    settings, _status = smtp_settings()
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
