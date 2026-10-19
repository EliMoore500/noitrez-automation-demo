import json
import os
import unittest
from email.message import EmailMessage
from unittest.mock import patch

import app


class ContactEndpointTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        app.contact_requests.clear()
        self.client = app.app.test_client()
        self.resend_environment = patch.dict(os.environ, {
            "RESEND_API_KEY": "re_test_key",
            "RESEND_FROM": "Noitrez <hello@noitrez.com>",
            "CONTACT_NOTIFICATION_EMAIL": "sales@noitrez.com",
        })
        self.resend_environment.start()
        self.addCleanup(self.resend_environment.stop)

    def payload(self, **overrides):
        fields = {
            "name": "Alex Example",
            "email": "alex@example.com",
            "business": "Example HVAC",
            "request": "We spend too long responding to service requests.",
        }
        fields.update(overrides)
        return fields

    @patch("app.send_email", return_value=(True, "Email sent successfully."))
    def test_valid_request_is_emailed_to_configured_recipient(self, send_email):
        response = self.client.post(
            "/api/contact",
            json=self.payload(),
            headers={"Origin": "https://noitrez.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        email, _settings = send_email.call_args.args
        self.assertEqual(email["To"], "sales@noitrez.com")
        self.assertEqual(email["Reply-To"], "alex@example.com")
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "https://noitrez.com",
        )

    @patch("app.send_email", return_value=(True, "Email sent successfully."))
    def test_contact_notification_defaults_to_sales_address(self, send_email):
        resend_environment = {
            "RESEND_API_KEY": "re_test_key",
            "RESEND_FROM": "Noitrez <hello@noitrez.com>",
        }
        with patch.dict(os.environ, resend_environment, clear=True):
            response = self.client.post("/api/contact", json=self.payload())

        self.assertEqual(response.status_code, 200)
        email, _settings = send_email.call_args.args
        self.assertEqual(email["To"], "sales@noitrez.com")

    @patch("app.send_email")
    def test_honeypot_is_accepted_without_sending(self, send_email):
        response = self.client.post("/api/contact", json=self.payload(website="bot"))

        self.assertEqual(response.status_code, 200)
        send_email.assert_not_called()

    @patch("app.send_email")
    def test_unapproved_origin_is_rejected(self, send_email):
        response = self.client.post(
            "/api/contact",
            json=self.payload(),
            headers={"Origin": "https://attacker.example"},
        )

        self.assertEqual(response.status_code, 403)
        send_email.assert_not_called()

    @patch("app.send_email")
    def test_invalid_email_is_rejected(self, send_email):
        response = self.client.post(
            "/api/contact",
            json=self.payload(email="not-an-email"),
        )

        self.assertEqual(response.status_code, 400)
        send_email.assert_not_called()

    def test_public_lead_management_routes_are_not_available(self):
        self.assertEqual(self.client.get("/api/leads").status_code, 404)
        self.assertEqual(
            self.client.patch("/api/leads/1", json={"status": "Won"}).status_code,
            404,
        )
        self.assertEqual(self.client.delete("/api/leads/1").status_code, 404)

    @patch("app.send_email", return_value=(True, "Email sent successfully."))
    def test_contact_requests_are_rate_limited(self, send_email):
        for _ in range(app.CONTACT_RATE_LIMIT):
            response = self.client.post("/api/contact", json=self.payload())
            self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/contact", json=self.payload())
        self.assertEqual(response.status_code, 429)
        self.assertEqual(send_email.call_count, app.CONTACT_RATE_LIMIT)

    @patch("app.send_email")
    def test_missing_resend_config_returns_actionable_error(self, send_email):
        with patch.dict(os.environ, {"RESEND_API_KEY": ""}):
            response = self.client.post("/api/contact", json=self.payload())

        self.assertEqual(response.status_code, 503)
        self.assertIn("sales@noitrez.com", response.json["error"])
        send_email.assert_not_called()

    @patch("app.urlopen")
    def test_resend_email_uses_https_and_bearer_authorization(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"id":"email_test_id"}'
        message = EmailMessage()
        message["Subject"] = "Test request"
        message["Reply-To"] = "alex@example.com"
        message.set_content("A test message.")
        settings = {
            "api_key": "re_test_key",
            "sender": "Noitrez <hello@noitrez.com>",
            "recipient": "sales@noitrez.com",
        }

        sent, _status = app.send_email(message, settings)

        self.assertTrue(sent)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.resend.com/emails")
        self.assertEqual(request.get_header("Authorization"), "Bearer re_test_key")
        body = json.loads(request.data)
        self.assertEqual(body["to"], ["sales@noitrez.com"])
        self.assertEqual(body["reply_to"], "alex@example.com")

    def test_allowed_origin_can_complete_cors_preflight(self):
        response = self.client.options(
            "/api/contact",
            headers={
                "Origin": "https://noitrez.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            response.headers["Access-Control-Allow-Origin"],
            "https://noitrez.com",
        )

    def test_demo_renders_as_sample_only(self):
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(page.count('data-scenario="'), 3)
        self.assertIn("no personal information is requested", page.lower())
        self.assertNotIn('id="lead-form"', page)
        self.assertNotIn("Saved inquiries", page)


if __name__ == "__main__":
    unittest.main()