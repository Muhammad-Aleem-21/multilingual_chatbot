"""
main.py  -  chat with the bot in the terminal.

Run it:      python main.py                 (chat, no documents)
             python main.py --rag           (also search data/docs, needs sentence-transformers)
             python main.py --rag --translate-queries   (extra help for Roman Urdu questions)

Type  /reset  to start over,  /quit  to leave.
"""

import argparse
import sys

from chatbot.chatbot import Chatbot
from chatbot.config import DEFAULT_MODEL
from chatbot.llm import LLMError


def main() -> None:
    # Make the terminal print Urdu letters properly.
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Multilingual (English / Urdu / Roman Urdu) chatbot")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Groq model name")
    parser.add_argument("--rag", action="store_true", help="answer using the documents in data/docs")
    parser.add_argument("--no-translate", action="store_true",
                        help="with --rag: do NOT also search with an English translation of the question")
    parser.add_argument("--translate-queries", action="store_true", help=argparse.SUPPRESS)  # old name, now the default
    args = parser.parse_args()

    retriever = None
    if args.rag:
        from chatbot.retrieval import Retriever   # imported only when needed (it is heavy)
        retriever = Retriever(use_query_translation=not args.no_translate)

    bot = Chatbot(model=args.model, retriever=retriever)
    print(f"DesiMart assistant ready (model: {args.model}). Type /quit to exit, /reset to restart.")
    print("Try: 'kya hal hai', 'mera order kahan hai', 'ڈیلیوری میں کتنے دن لگتے ہیں؟'\n")

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_text:
            continue
        if user_text == "/quit":
            break
        if user_text == "/reset":
            bot.reset()
            print("(conversation reset)\n")
            continue

        try:
            reply = bot.reply(user_text)
        except LLMError as error:
            print(f"Error: {error}\n")
            continue

        print(f"   [detected: {reply.detection.label} -> replying in: {reply.language}]")
        print(f"Bot: {reply.text}")
        if reply.sources:
            print(f"   [used documents: {', '.join(reply.sources)}]")
        print()


if __name__ == "__main__":
    main()