"""
check_retrieval.py  -  "WHY did the bot find (or not find) a document for my question?"

It shows the real similarity scores, so you can see what the search is doing.
Scores go from 0 (unrelated) to 1 (same meaning). A chunk is only given to the bot if its
score is at least MIN_SCORE (chatbot/config.py).

Run (needs your Groq key for the translation part):

    python -m evaluation.check_retrieval
    python -m evaluation.check_retrieval "کیا آپ کیش آن ڈیلیوری لیتے ہیں؟" "cash on delivery hai?"

For each question it prints the top matches
    1) searching with the question exactly as typed
    2) searching with its English translation
    3) the combined result the chatbot actually uses
"""

import sys

from chatbot.config import MIN_SCORE
from chatbot.language_detect import detect_language
from chatbot.llm import LLMError
from chatbot.retrieval import Retriever

DEFAULT_QUESTIONS = [
    "کیا آپ کیش آن ڈیلیوری لیتے ہیں؟",
    "cash on delivery available hai?",
    "Do you take cash on delivery?",
]


def show_top(retriever: Retriever, scores, title: str, k: int = 3) -> None:
    print(f"  {title}")
    for index in scores.argsort()[::-1][:k]:
        chunk = retriever.chunks[index]
        mark = "✓" if scores[index] >= MIN_SCORE else "✗ below MIN_SCORE"
        print(f"    {scores[index]:.2f} {mark:<18} {chunk.source}: {chunk.text[:60]}...")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    retriever = Retriever(use_query_translation=True)
    print(f"\nMIN_SCORE = {MIN_SCORE} (chunks scoring lower are ignored)\n")

    for question in questions:
        detection = detect_language(question)
        print(f"QUESTION: {question}   [detected: {detection.label}]")
        queries = retriever.queries_for(question)
        if len(queries) == 1 and detection.reply_language in ("urdu", "roman_urdu"):
            reason = retriever.last_translation_error or "the translation was identical to the question"
            print(f"  ⚠️ NO English translation was used. Reason: {reason}")
            print(f"     (models tried: {retriever.translate_models})")
        show_top(retriever, retriever.score_all(queries[0]), "as typed:")
        if len(queries) > 1:
            print(f"  English translation: {queries[1]}")
            show_top(retriever, retriever.score_all(queries[1]), "translated:")
        found = retriever.search(question)
        print("  => given to the bot:", [chunk.source for chunk in found] or "NOTHING (the bot will say it does not know)")
        print()


if __name__ == "__main__":
    try:
        main()
    except LLMError as error:
        print(f"Error: {error}")