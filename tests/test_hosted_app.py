"""Offline tests for the small free-hosting API."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import flask
except ImportError as error:
    raise unittest.SkipTest("Install requirements-hosted.txt for hosted API checks") from error

from hosted_app import create_app, excerpts, reply, validate


class TestHostedApp(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {"WEBSITE_API_TOKENS": "t" * 40,
            "WEBSITE_QUOTA_DB": str(Path(self.folder.name) / "usage.sqlite3"),
            "QUESTIONS_PER_HOUR": "1", "TOTAL_QUESTIONS_PER_HOUR": "2"})
        self.environment.start()
        self.client = create_app().test_client()
        self.headers = {"Authorization": "Bearer " + "t" * 40}
        self.data = {"question": "What is the university name?", "pages": [
            {"url": "https://example.com/", "text": "Example University. Alumni: 195,000."}], "history": []}

    def tearDown(self):
        self.environment.stop()
        self.folder.cleanup()

    def test_health_and_authentication(self):
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})
        with patch("hosted_app.reply") as mocked:
            self.assertEqual(self.client.post("/chat", json=self.data).status_code, 401)
            mocked.assert_not_called()

    def test_answer_and_durable_quota(self):
        with patch("hosted_app.reply", return_value={"text": "Example University"}) as mocked:
            response = self.client.post("/chat", json=self.data, headers=self.headers)
            self.assertEqual(response.json["text"], "Example University")
            # Recreating the app must not reset a token's quota.
            second = create_app().test_client()
            self.assertEqual(second.post("/chat", json=self.data, headers=self.headers).status_code, 429)
            self.assertEqual(mocked.call_count, 1)

    def test_invalid_cross_site_data_is_rejected(self):
        self.data["pages"].append({"url": "https://other.com/", "text": "Private record"})
        self.assertEqual(self.client.post("/chat", json=self.data, headers=self.headers).status_code, 400)

    def test_no_configuration_fails_closed(self):
        with patch.dict(os.environ, {"WEBSITE_API_TOKENS": ""}):
            with self.assertRaises(RuntimeError):
                create_app()

    def test_search_finds_fact_beyond_current_page_prefix(self):
        self.data["pages"][0]["text"] = "Unrelated introduction. " * 1000 + "Alumni count is 195,000."
        context, sources = excerpts(self.data["pages"], "alumni count", "https://example.com/")
        self.assertIn("195,000", context)
        self.assertEqual(sources, ["https://example.com/"])

    def test_roman_urdu_is_translated_for_cross_page_search(self):
        self.data["question"] = "alumni ki tadad kia hai"
        self.data["pages"].append({"url": "https://example.com/about", "text": "There are 195,000 alumni."})
        self.data["current_url"] = "https://example.com/"
        with patch("hosted_app.llm.chat", side_effect=["What is the alumni count?", "195,000 alumni hain."]) as chat:
            result = reply(self.data)
        self.assertEqual(result["language"], "roman_urdu")
        self.assertIn("https://example.com/about", result["sources"])
        self.assertIn("195,000", chat.call_args.args[0][0]["content"])

    def test_internal_errors_do_not_leak_credentials(self):
        with patch("hosted_app.reply", side_effect=RuntimeError("secret-api-key")):
            response = self.client.post("/chat", json=self.data, headers=self.headers)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("secret-api-key", response.get_data(as_text=True))
