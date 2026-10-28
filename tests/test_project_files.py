"""
Tests that check our DATA files and the chatbot's wiring - also offline.
The Groq call is replaced by a fake so no API key is needed ("mocking").
"""

import unittest
from unittest import mock

from chatbot import chatbot as chatbot_module
from chatbot.config import DOCS_DIR, EVAL_SET_PATH, LANGUAGES, RETRIEVAL_EVAL_PATH
from evaluation.common import load_json


class TestEvalSet(unittest.TestCase):
    def setUp(self):
        self.eval_set = load_json(EVAL_SET_PATH)

    def test_has_at_least_50_messages(self):
        self.assertGreaterEqual(len(self.eval_set), 50)

    def test_ids_are_unique(self):
        ids = [item["id"] for item in self.eval_set]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_item_has_the_needed_fields(self):
        for item in self.eval_set:
            for key in ("id", "text", "type", "reply_lang", "meaning", "group"):
                self.assertIn(key, item, f"item {item.get('id')} misses '{key}'")
            self.assertIn(item["reply_lang"], LANGUAGES)

    def test_covers_all_message_types(self):
        types = {item["type"] for item in self.eval_set}
        self.assertTrue({"english", "urdu", "roman_urdu", "mixed"} <= types)

    def test_contains_the_spelling_variations_from_the_brief(self):
        texts = {item["text"] for item in self.eval_set}
        self.assertIn("kya hal hai", texts)
        self.assertIn("kia haal hai", texts)


class TestRetrievalData(unittest.TestCase):
    def test_every_expected_document_exists(self):
        existing = {path.name for path in DOCS_DIR.glob("*.txt")}
        for item in load_json(RETRIEVAL_EVAL_PATH):
            self.assertIn(item["expected_source"], existing)

    def test_has_urdu_questions(self):
        types = {item["type"] for item in load_json(RETRIEVAL_EVAL_PATH)}
        self.assertIn("urdu", types)


class TestChatbotWiring(unittest.TestCase):
    def test_system_prompt_contains_the_reply_language_rule(self):
        prompt = chatbot_module.build_system_prompt("roman_urdu")
        self.assertIn("Roman Urdu", prompt)
        self.assertNotIn("{", prompt)    # no unfilled placeholders left over

    def test_documents_are_put_into_the_prompt(self):
        from chatbot.retrieval import Chunk
        chunk = Chunk("Delivery: 2 to 3 days", "delivery.txt", 0.9)
        prompt = chatbot_module.build_system_prompt("english", [chunk])
        self.assertIn("2 to 3 days", prompt)

    def test_reply_uses_detected_language_and_remembers_history(self):
        with mock.patch.object(chatbot_module.llm, "chat", return_value="fake answer") as fake:
            bot = chatbot_module.Chatbot()
            result = bot.reply("mera order kahan hai")
            self.assertEqual(result.language, "roman_urdu")
            self.assertEqual(result.text, "fake answer")
            system_message = fake.call_args.args[0][0]["content"]
            self.assertIn("Roman Urdu", system_message)

            bot.reply("Where is my order?")
            self.assertEqual(len(bot.history), 4)   # 2 turns x (user + assistant)


if __name__ == "__main__":
    unittest.main()
