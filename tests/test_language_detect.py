"""
Tests for the language detector. They need NO internet and NO API key.

Run them:   python -m unittest discover -s tests -t . -v
(or in VS Code: Testing panel on the left -> Run)

A "test" is a tiny function that checks: "when I give the code THIS, do I get THAT?"
If someone later changes the word lists and breaks something, a test turns red.
"""

import unittest

from chatbot.language_detect import (
    ENGLISH_WORDS,
    ROMAN_URDU_WORDS,
    LanguageTracker,
    detect_language,
    detect_language_request,
)


class TestWordLists(unittest.TestCase):
    def test_lists_do_not_overlap(self):
        # A word must not be in both lists, otherwise the decision would be random.
        self.assertEqual(ROMAN_URDU_WORDS & ENGLISH_WORDS, set())


class TestDetectLanguage(unittest.TestCase):
    def reply_for(self, text):
        return detect_language(text).reply_language

    def test_english(self):
        self.assertEqual(self.reply_for("Where is my order?"), "english")

    def test_urdu_script(self):
        self.assertEqual(self.reply_for("آپ کیسے ہیں؟"), "urdu")

    def test_roman_urdu_spelling_variations(self):
        # The spelling variants named in the project description.
        for text in ["kya hal hai", "kia haal hai", "kya haal hai", "kia hal hy"]:
            self.assertEqual(self.reply_for(text), "roman_urdu", text)

    def test_repeated_letters_are_squeezed(self):
        self.assertEqual(self.reply_for("kyaaaaa haaal hai"), "roman_urdu")

    def test_typo_is_caught_by_fuzzy_matching(self):
        # "delivry" is a typo of "delivery"; it should still count as an English word.
        self.assertEqual(detect_language("delivry").label, "english")

    def test_mixed_roman_urdu_and_english_replies_in_roman_urdu(self):
        d = detect_language("Mera order abhi tak nahi aaya, please check karo")
        self.assertEqual(d.label, "mixed")
        self.assertEqual(d.reply_language, "roman_urdu")

    def test_mixed_urdu_script_and_english_replies_in_urdu(self):
        d = detect_language("میرا order ابھی تک deliver نہیں ہوا")
        self.assertEqual(d.label, "mixed")
        self.assertEqual(d.reply_language, "urdu")

    def test_mostly_english_with_one_urdu_word_replies_in_english(self):
        self.assertEqual(self.reply_for("Please check my order status bhai"), "english")

    def test_nothing_recognisable_is_unknown(self):
        d = detect_language("🙂 12345")
        self.assertEqual(d.label, "unknown")
        self.assertIsNone(d.reply_language)

    def test_urdu_question_mark_alone_is_not_a_word(self):
        self.assertEqual(detect_language("؟").label, "unknown")


class TestLanguageRequest(unittest.TestCase):
    def test_requests(self):
        self.assertEqual(detect_language_request("please reply in English"), "english")
        self.assertEqual(detect_language_request("english mein jawab do"), "english")
        self.assertEqual(detect_language_request("roman urdu mein baat karo"), "roman_urdu")
        self.assertEqual(detect_language_request("اردو میں جواب دیں"), "urdu")

    def test_normal_messages_are_not_requests(self):
        self.assertIsNone(detect_language_request("Where is my order?"))
        self.assertIsNone(detect_language_request("mera order kahan hai"))


class TestLanguageTracker(unittest.TestCase):
    def test_follows_the_user(self):
        tracker = LanguageTracker()
        self.assertEqual(tracker.update("mera order kahan hai"), "roman_urdu")
        self.assertEqual(tracker.update("Where is my order?"), "english")

    def test_tiny_english_message_does_not_switch_language(self):
        tracker = LanguageTracker()
        tracker.update("mera order kahan hai")
        self.assertEqual(tracker.update("ok thanks"), "roman_urdu")

    def test_unrecognisable_message_keeps_previous_language(self):
        tracker = LanguageTracker()
        tracker.update("آپ کیسے ہیں؟")
        self.assertEqual(tracker.update("👍"), "urdu")

    def test_explicit_request_sticks(self):
        tracker = LanguageTracker()
        tracker.update("please reply in English")
        self.assertEqual(tracker.update("mera order kahan hai"), "english")
        self.assertEqual(tracker.update("roman urdu mein jawab do"), "roman_urdu")


if __name__ == "__main__":
    unittest.main()
