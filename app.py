import json
import os
import smtplib
import sqlite3
from datetime import datetime, timezone
from email.message import EmailMessage

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

load_dotenv(dotenv_path=".env")

app = Flask(__name__)
DB_PATH = os.path.join("data", "leads.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs("data", exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            service TEXT,
            message TEXT,
            temperature TEXT,
            urgency TEXT,
            summary TEXT,
            customer_reply TEXT,
            ai_raw TEXT
        )
    """)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(leads)").fetchall()
    }
    if "status" not in columns:
        conn.execute("ALTER TABLE leads ADD COLUMN status TEXT NOT NULL DEFAULT 'New'")
    conn.commit()
    conn.close()


init_db()


def analyze_lead(name, email, phone, service, message):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key.startswith("PASTE_"):
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Add it to the local .env file "
            "or to the deployment service's environment variables."
        )

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    prompt = f"""
You are an AI lead-intake assistant for a fictional Northern Virginia HVAC company.

Analyze this incoming customer lead.

Customer name: {name}
Email: {email}
Phone: {phone}
Requested service: {service}
Customer message: {message}

Return ONLY valid JSON with exactly these keys:
temperature: one of "Hot", "Warm", "Cold"
urgency: one of "Emergency", "Urgent", "Normal", "Low"
service_type: short description
summary: one concise sentence for the business
customer_reply: a professional, friendly reply to the customer. Do not promise a specific appointment time or price.
reason: one short sentence explaining the temperature classification.

Rules:
- Hot means the business should contact the customer very soon because the lead is highly likely to need service now.
- Warm means a legitimate lead that should be followed up.
- Cold means low urgency, weak intent, or mostly informational.
- Treat safety-related HVAC problems as urgent, but do not provide dangerous repair instructions.
"""

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    text = response.output_text.strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # Handle occasional markdown fences defensively.
        cleaned = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(cleaned)

    required = {
        "temperature", "urgency", "service_type",
        "summary", "customer_reply", "reason"
    }
    missing = required - result.keys()
    if missing:
        raise RuntimeError(f"AI response is missing fields: {', '.join(sorted(missing))}")

    return result


def save_lead(lead, ai):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO leads (
            created_at, name, email, phone, service, message,
            temperature, urgency, summary, customer_reply, ai_raw
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now(timezone.utc).isoformat(),
        lead["name"], lead["email"], lead["phone"],
        lead["service"], lead["message"],
        ai["temperature"], ai["urgency"], ai["summary"],
        ai["customer_reply"], json.dumps(ai)
    ))
    conn.commit()
    lead_id = cur.lastrowid
    conn.close()
    return lead_id


def format_priority(value):
    return {
        "Hot": "High Priority",
        "Warm": "Medium Priority",
        "Cold": "Low Priority",
    }.get(value, value)


def smtp_settings():
    if os.getenv("SMTP_ENABLED", "false").lower() != "true":
        return None, "SMTP email is disabled. Lead was saved successfully."

    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    sender = os.getenv("SMTP_FROM", username).strip()
    password = "".join(os.getenv("SMTP_PASSWORD", "").split())
    recipient = os.getenv("BUSINESS_NOTIFICATION_EMAIL", "").strip()
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


def send_business_email(lead, ai, settings):
    priority = format_priority(ai["temperature"])
    recommended_action = {
        "Hot": "Contact within 15 minutes.",
        "Warm": "Follow up today.",
        "Cold": "Add to a future follow-up list.",
    }.get(ai["temperature"], "Review and follow up.")

    msg = EmailMessage()
    msg["Subject"] = f"[Noitrez] New {priority} Lead - {lead['name']}"
    msg["From"] = settings["sender"]
    msg["To"] = settings["recipient"]
    msg.set_content(f"""New lead received.

New {priority} Lead

{lead['name']}
{lead['service']}
{lead['phone'] or 'Phone not provided'}

AI Summary: {ai['summary']}

Recommended action: {recommended_action}

Details:
Urgency: {ai['urgency']}
Service type: {ai.get('service_type', lead.get('service', ''))}
Customer email: {lead['email']}

Message:
{lead['message']}

AI summary:
{ai['summary']}

Why:
{ai['reason']}

Suggested customer reply:
{ai['customer_reply']}
""")
    return send_email(msg, settings)


def send_customer_reply_email(lead, ai, settings):
    msg = EmailMessage()
    msg["Subject"] = "Thanks for contacting Noitrez"
    msg["From"] = settings["sender"]
    msg["To"] = lead["email"]
    msg.set_content(f"""Hi {lead['name']},

{ai['customer_reply']}

Your request: {lead['service']}

Noitrez
""")
    return send_email(msg, settings)


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/leads")
def create_lead():
    data = request.get_json(silent=True) or {}

    required = ["name", "email", "service", "message"]
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    lead = {
        "name": str(data["name"]).strip(),
        "email": str(data["email"]).strip(),
        "phone": str(data.get("phone", "")).strip(),
        "service": str(data["service"]).strip(),
        "message": str(data["message"]).strip(),
    }

    try:
        ai = analyze_lead(**lead)
        lead_id = save_lead(lead, ai)
        settings, settings_status = smtp_settings()
        if settings is None:
            email_sent = False
            email_status = settings_status
            customer_email_sent = False
            customer_email_status = settings_status
        else:
            email_sent, email_status = send_business_email(lead, ai, settings)
            if email_sent and os.getenv("CUSTOMER_REPLY_ENABLED", "true").lower() == "true":
                customer_email_sent, customer_email_status = send_customer_reply_email(
                    lead, ai, settings
                )
            elif not email_sent:
                customer_email_sent = False
                customer_email_status = "Customer reply was not sent because staff notification failed."
            else:
                customer_email_sent = False
                customer_email_status = "Customer reply email is disabled."

        return jsonify({
            "success": True,
            "lead_id": lead_id,
            "lead": lead,
            "analysis": ai,
            "email_sent": email_sent,
            "email_status": email_status,
            "customer_email_sent": customer_email_sent,
            "customer_email_status": customer_email_status,
        })
    except Exception as exc:
        app.logger.exception("Lead processing failed")
        return jsonify({"error": str(exc)}), 500


@app.get("/api/leads")
def list_leads():
    conn = get_db()
    rows = conn.execute("""
        SELECT id, created_at, name, email, phone, service,
               message, temperature, urgency, summary, status
        FROM leads
        ORDER BY id DESC
        LIMIT 100
    """).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.patch("/api/leads/<int:lead_id>")
def update_lead(lead_id):
    data = request.get_json(silent=True) or {}
    status = str(data.get("status", "")).strip()
    allowed_statuses = {"New", "Contacted", "Scheduled", "Won", "Lost"}
    if status not in allowed_statuses:
        return jsonify({"error": "Invalid lead status"}), 400

    conn = get_db()
    cursor = conn.execute(
        "UPDATE leads SET status = ? WHERE id = ?",
        (status, lead_id),
    )
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return jsonify({"error": "Lead not found"}), 404

    return jsonify({"success": True, "lead_id": lead_id, "status": status})


@app.delete("/api/leads/<int:lead_id>")
def delete_lead(lead_id):
    conn = get_db()
    cursor = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()

    if cursor.rowcount == 0:
        return jsonify({"error": "Lead not found"}), 404

    return jsonify({"success": True, "lead_id": lead_id})


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
