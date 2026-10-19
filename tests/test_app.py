import unittest

import app


class DemoPageTests(unittest.TestCase):
    def setUp(self):
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()
    def test_demo_renders_as_sample_only(self):
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(page.count('data-scenario="'), 3)
        self.assertIn("no personal information is requested", page.lower())
        self.assertNotIn('id="lead-form"', page)
        self.assertNotIn('id="contact-form"', page)
        self.assertNotIn("Saved inquiries", page)
        self.assertNotIn('action="/api/contact"', page)
        self.assertNotIn("fetch(", page)

    def test_contact_data_api_is_not_exposed(self):
        self.assertEqual(self.client.post("/api/contact", json={}).status_code, 404)

    def test_health_check(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()