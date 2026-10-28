import os
import unittest
from unittest.mock import patch

import app


class DemoAIAnalysisTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        if hasattr(app, "analysis_requests"):
            app.analysis_requests.clear()
        self.client = app.app.test_client()

    def payload(self, **overrides):
        values = {
            "name": "Sample Visitor",
            "email": "sample@example.test",
            "phone": "703-555-0100",
            "service": "AC repair",
            "message": "The AC stopped cooling this afternoon. Please contact me about an appointment.",
        }
        values.update(overrides)
        return values

    def analysis(self):
        return {
            "temperature": "Hot",
            "urgency": "Urgent",
            "service_type": "AC repair",
            "summary": "Cooling has stopped and the customer wants an appointment.",
            "reason": "The request reports an active loss of cooling and asks for follow-up.",
            "customer_reply": "Thanks for reaching out. Our team will review your request and follow up about availability.",
        }

    @patch("app.analyze_lead")
    def test_valid_lead_returns_ai_analysis_without_storing_or_emailing(self, analyze_lead):
        analyze_lead.return_value = self.analysis()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            response = self.client.post("/api/analyze", json=self.payload())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["analysis"], self.analysis())
        self.assertNotIn("lead_id", response.json)
        analyze_lead.assert_called_once_with(
            name="Sample Visitor",
            service="AC repair",
            message=self.payload()["message"],
        )

    @patch("app.analyze_lead")
    def test_missing_openai_key_returns_service_unavailable(self, analyze_lead):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            response = self.client.post("/api/analyze", json=self.payload())

        self.assertEqual(response.status_code, 503)
        analyze_lead.assert_not_called()

    @patch("app.analyze_lead")
    def test_invalid_email_is_rejected_before_ai_request(self, analyze_lead):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            response = self.client.post(
                "/api/analyze",
                json=self.payload(email="not-an-email"),
            )

        self.assertEqual(response.status_code, 400)
        analyze_lead.assert_not_called()

    @patch("app.analyze_lead")
    def test_analysis_requests_are_rate_limited(self, analyze_lead):
        analyze_lead.return_value = self.analysis()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            for _ in range(app.ANALYSIS_RATE_LIMIT):
                response = self.client.post("/api/analyze", json=self.payload())
                self.assertEqual(response.status_code, 200)

            response = self.client.post("/api/analyze", json=self.payload())

        self.assertEqual(response.status_code, 429)
        self.assertEqual(analyze_lead.call_count, app.ANALYSIS_RATE_LIMIT)

    def test_demo_renders_live_form_and_sample_scenarios(self):
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(page.count('data-scenario="'), 3)
        self.assertIn('id="lead-form"', page)
        self.assertIn('id="download-sheet"', page)
        self.assertNotIn("Load a sample workflow", page)
        self.assertIn('name="service"', page)
        self.assertIn('name="message"', page)
        self.assertIn("OpenAI", page)
        self.assertIn("nothing was emailed or saved", page.lower())

    def test_contact_email_api_remains_disabled(self):
        self.assertEqual(self.client.post("/api/contact", json={}).status_code, 404)

    def test_health_check(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()