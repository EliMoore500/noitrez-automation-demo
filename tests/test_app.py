import os
import unittest
from unittest.mock import patch

import app


class ContactEndpointTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        app.contact_requests.clear()
        self.client = app.app.test_client()
        self.smtp_environment = patch.dict(os.environ, {
            "SMTP_ENABLED": "true",
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "sender@example.test",
            "SMTP_FROM": "sender@example.test",
            "SMTP_PASSWORD": "test-password",
            "CONTACT_NOTIFICATION_EMAIL": "sales@noitrez.com",
        })
        self.smtp_environment.start()
        self.addCleanup(self.smtp_environment.stop)

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
        smtp_environment = {
            "SMTP_ENABLED": "true",
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "sender@example.test",
            "SMTP_FROM": "sender@example.test",
            "SMTP_PASSWORD": "test-password",
        }
        with patch.dict(os.environ, smtp_environment, clear=True):
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
    def test_disabled_smtp_returns_actionable_error(self, send_email):
        with patch.dict(os.environ, {"SMTP_ENABLED": "false"}):
            response = self.client.post("/api/contact", json=self.payload())

        self.assertEqual(response.status_code, 503)
        self.assertIn("sales@noitrez.com", response.json["error"])
        send_email.assert_not_called()

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