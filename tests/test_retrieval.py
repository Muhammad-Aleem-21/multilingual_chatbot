"""
Tests for the document search (chatbot/retrieval.py). No internet, no model download:
a FAKE embedding model gives every text a hand-made vector, so we control which chunk
"looks" most similar and can check what search() does with it.
"""

import unittest

import numpy as np

from chatbot.retrieval import DOC_EXPAND_MAX_CHARS, Chunk, Retriever, chunk_text


class FakeModel:
    """encode(text) -> a vector chosen by us. Unknown texts get the 'question' vector."""

    def __init__(self, table, question_vector):
        self.table, self.question_vector = table, question_vector

    def encode(self, texts, normalize_embeddings=True):
        out = np.array([self.table.get(t, self.question_vector) for t in texts], dtype=float)
        return out / np.linalg.norm(out, axis=1, keepdims=True)


def make_retriever(chunks, vectors, question_vector):
    table = {chunk.text: vector for chunk, vector in zip(chunks, vectors)}
    return Retriever(chunks=chunks, model=FakeModel(table, question_vector),
                     use_query_translation=False)


class TestSearchExpansion(unittest.TestCase):
    def test_short_document_is_returned_whole_even_if_key_paragraph_scores_lowest(self):
        # The situation from the bug report: the "7 days" paragraph is the LEAST similar of
        # the 4 return-policy paragraphs, so "top 3" alone would have dropped it.
        chunks = [
            Chunk("Return policy: You can return most items within 7 days.", "return_policy.txt"),
            Chunk("Return policy: Damaged items can be exchanged free.", "return_policy.txt"),
            Chunk("Return policy: Refunds take 5 to 7 working days.", "return_policy.txt"),
            Chunk("Return policy: Underwear cannot be returned.", "return_policy.txt"),
            Chunk("Delivery: Orders arrive in 2 to 3 days.", "delivery.txt"),
        ]
        vectors = [[0.5, 1, 0], [1, 0.2, 0], [0.9, 0.3, 0], [0.8, 0.4, 0], [0, 0, 1]]
        retriever = make_retriever(chunks, vectors, [1, 0, 0])

        found = retriever.search("anything", k=3, min_score=0.1)
        texts = [chunk.text for chunk in found]
        self.assertIn("Return policy: You can return most items within 7 days.", texts)
        self.assertEqual({c.source for c in found}, {"return_policy.txt"})
        self.assertEqual(len(found), 4)

    def test_unrelated_documents_are_not_added(self):
        chunks = [Chunk("A: apples", "a.txt"), Chunk("B: boats", "b.txt")]
        retriever = make_retriever(chunks, [[1, 0], [0, 1]], [1, 0])
        found = retriever.search("apples", k=3, min_score=0.5)
        self.assertEqual([c.source for c in found], ["a.txt"])

    def test_nothing_above_min_score_returns_nothing(self):
        chunks = [Chunk("A: apples", "a.txt")]
        retriever = make_retriever(chunks, [[0, 1]], [1, 0])
        self.assertEqual(retriever.search("x", min_score=0.5), [])

    def test_best_document_comes_first(self):
        chunks = [Chunk("A: one", "a.txt"), Chunk("B: two", "b.txt")]
        retriever = make_retriever(chunks, [[0.6, 1], [1, 0.1]], [1, 0])
        found = retriever.search("x", k=2, min_score=0.1)
        self.assertEqual(found[0].source, "b.txt")

    def test_long_document_returns_hit_plus_neighbours_only(self):
        big = "x" * (DOC_EXPAND_MAX_CHARS // 4)            # 5 chunks of this size = too long
        chunks = [Chunk(f"{i}: {big}", "big.pdf") for i in range(6)]
        vectors = [[0, 1]] * 6
        vectors[3] = [1, 0]                                 # chunk 3 is the hit
        retriever = make_retriever(chunks, vectors, [1, 0])
        found = retriever.search("x", k=1, min_score=0.5)
        self.assertEqual(sorted(c.text[0] for c in found), ["2", "3", "4"])


class TestChunkText(unittest.TestCase):
    def test_short_paragraphs_stay_whole(self):
        chunks = chunk_text("First paragraph.\n\nSecond paragraph.", "f.txt")
        self.assertEqual(len(chunks), 2)

    def test_long_paragraph_is_cut(self):
        chunks = chunk_text("Sentence one is here. " * 100, "f.txt", max_chars=200)
        self.assertGreater(len(chunks), 5)
        self.assertTrue(all(len(c.text) <= 200 + len("f.txt: ") for c in chunks))


if __name__ == "__main__":
    unittest.main()


class TestTranslation(unittest.TestCase):
    """The English-translation step must survive 'thinking' models and show failures."""

    def make(self):
        chunks = [Chunk("Return: 7 days", "r.txt")]
        retriever = make_retriever(chunks, [[1, 0]], [1, 0])
        retriever.use_query_translation = True
        retriever.translate_models = ["thinker", "plain"]
        return retriever

    def test_clean_translation_removes_hidden_reasoning(self):
        from chatbot.retrieval import clean_translation
        self.assertEqual(clean_translation("<think>hmm hmm</think>\nHow many days?"), "How many days?")
        self.assertEqual(clean_translation('"How many days?"'), "How many days?")
        self.assertEqual(clean_translation("<think>never finished"), "")
        self.assertEqual(clean_translation(""), "")

    def test_empty_answer_falls_back_to_next_model(self):
        from unittest import mock
        retriever = self.make()
        answers = {"thinker": "", "plain": "Within how many days can an item be returned?"}
        with mock.patch("chatbot.retrieval.llm.chat", side_effect=lambda m, model, **k: answers[model]):
            queries = retriever.queries_for("cheex kitne din k ander wapsi ho skti h?")
        self.assertEqual(queries[1], "Within how many days can an item be returned?")
        self.assertEqual(retriever.last_translation_error, "")

    def test_failure_is_reported_not_hidden(self):
        from unittest import mock
        from chatbot.llm import LLMError
        retriever = self.make()

        def fake(messages, model, **kwargs):
            if model == "thinker":
                return ""
            raise LLMError("model not found")
        with mock.patch("chatbot.retrieval.llm.chat", side_effect=fake):
            queries = retriever.queries_for("cheex kitne din k ander wapsi ho skti h?")
        self.assertEqual(len(queries), 1)                       # only the original question
        self.assertIn("thinker: returned an empty answer", retriever.last_translation_error)
        self.assertIn("plain: model not found", retriever.last_translation_error)

    def test_english_question_is_never_translated(self):
        from unittest import mock
        retriever = self.make()
        with mock.patch("chatbot.retrieval.llm.chat") as chat:
            queries = retriever.queries_for("How many days can I return an item?")
        chat.assert_not_called()
        self.assertEqual(len(queries), 1)