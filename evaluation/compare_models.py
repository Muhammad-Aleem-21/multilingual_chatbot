"""
compare_models.py  -  which Groq model handles Urdu / Roman Urdu better?

For EVERY message in data/eval_set.json and for EVERY model we do this:

    1. Ask the model to answer, using the correct reply language
       (we use the human-written "reply_lang", so we test the MODEL, not our detector).
    2. Check A: did the reply really come out in the requested language?
       (done by our own detector - free, no AI needed)
    3. Check B: ask a third "judge" model to give two scores from 1 to 5:
         - understanding     did the reply address what the user really meant?
         - language_quality  is the reply natural, correct, in the right script?
    4. Print a summary table and save everything in results/.

Run it (needs your Groq key):

    python -m evaluation.compare_models                  # all 70 messages
    python -m evaluation.compare_models --limit 10       # quick test with 10 messages
    python -m evaluation.compare_models --no-judge       # only the free language check
    python -m evaluation.compare_models --models llama-3.3-70b-versatile llama-3.1-8b-instant

Tip: Groq's free plan has speed limits. The script waits between calls and retries
automatically, so a full run takes a few minutes.
"""

import argparse
import csv
import json
import re
import time

from chatbot import llm
from chatbot.chatbot import build_system_prompt
from chatbot.config import EVAL_SET_PATH, JUDGE_MODEL, MODELS_TO_COMPARE, RESULTS_DIR
from chatbot.language_detect import detect_language
from evaluation.common import group_by, load_json, percent, save_json

LANGUAGE_NAMES = {
    "english": "English",
    "urdu": "Urdu (Urdu script)",
    "roman_urdu": "Roman Urdu (Urdu in English letters)",
}

JUDGE_SYSTEM = """You are a strict evaluator of a customer-support chatbot for an online store in Pakistan.
You understand English, Urdu and Roman Urdu. Score the bot's reply from 1 (very bad) to 5 (excellent):

- understanding: did the reply correctly address what the user MEANT? (1 = misunderstood or off-topic)
- language_quality: is the reply written naturally and correctly in the REQUIRED reply language,
  in the right script, with believable spelling and grammar? (1 = wrong language/script or gibberish)

The shop's documents are NOT given to the bot, so a polite "please contact support / I don't have that
information" is acceptable and should not be punished when the bot cannot know the answer.

Answer with JSON only: {"understanding": <1-5>, "language_quality": <1-5>, "comment": "<max 15 words>"}"""


def ask_model(model: str, text: str, language: str) -> tuple:
    """Get one reply from `model`. Returns (reply_text, seconds_taken)."""
    messages = [
        {"role": "system", "content": build_system_prompt(language)},
        {"role": "user", "content": text},
    ]
    start = time.time()
    reply = llm.chat(messages, model=model, temperature=0.3, max_tokens=400)
    return reply, round(time.time() - start, 2)


def judge(item: dict, reply: str, judge_model: str) -> dict:
    """Ask the judge model for scores. Returns {"understanding", "language_quality", "comment"}."""
    prompt = (
        f"User message: {item['text']}\n"
        f"What the user means (English): {item['meaning']}\n"
        f"Required reply language: {LANGUAGE_NAMES[item['reply_lang']]}\n"
        f"Bot reply: {reply}"
    )
    raw = llm.chat(
        [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}],
        model=judge_model, temperature=0, max_tokens=1500, json_mode=True,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Sometimes models wrap JSON in extra text. Pull out the {...} part.
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"understanding": None, "language_quality": None, "comment": "judge output unreadable"}


def average(values: list) -> float:
    values = [v for v in values if isinstance(v, (int, float))]
    return sum(values) / len(values) if values else float("nan")


def print_summary(rows: list, models: list, use_judge: bool) -> None:
    print("\n" + "=" * 78)
    print("SUMMARY (language_ok = reply was in the requested language; scores are 1-5)")
    print("=" * 78)
    header = f"{'model':<28}{'language_ok':>12}"
    if use_judge:
        header += f"{'understand':>12}{'lang_qual':>11}"
    header += f"{'avg sec':>9}"
    print(header)
    for model in models:
        mine = [r for r in rows if r["model"] == model]
        ok = sum(r["language_ok"] for r in mine)
        line = f"{model:<28}{percent(ok, len(mine)):>12}"
        if use_judge:
            line += f"{average([r['understanding'] for r in mine]):>12.2f}"
            line += f"{average([r['language_quality'] for r in mine]):>11.2f}"
        line += f"{average([r['seconds'] for r in mine]):>9.2f}"
        print(line)

    print("\nBy message type (type: language_ok" + (" / understanding)" if use_judge else ")"))
    for type_name, type_rows in sorted(group_by(rows, "type").items()):
        parts = []
        for model in models:
            mine = [r for r in type_rows if r["model"] == model]
            ok = sum(r["language_ok"] for r in mine)
            text = f"{percent(ok, len(mine)).strip()}"
            if use_judge:
                text += f" / {average([r['understanding'] for r in mine]):.2f}"
            parts.append(f"{model}: {text}")
        print(f"  {type_name:<11} " + "   |   ".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Groq models on Urdu / Roman Urdu input")
    parser.add_argument("--models", nargs="+", default=MODELS_TO_COMPARE)
    parser.add_argument("--judge", default=JUDGE_MODEL, help="model that scores the replies")
    parser.add_argument("--no-judge", action="store_true", help="skip the AI judge")
    parser.add_argument("--limit", type=int, default=None, help="only use the first N messages")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds to wait between calls")
    args = parser.parse_args()

    eval_set = load_json(EVAL_SET_PATH)
    if args.limit:
        eval_set = eval_set[: args.limit]
    use_judge = not args.no_judge

    print(f"Comparing {args.models} on {len(eval_set)} messages"
          + (f" (judge: {args.judge})" if use_judge else " (no judge)"))

    rows = []
    for model in args.models:
        print(f"\n--- {model} ---")
        for number, item in enumerate(eval_set, start=1):
            reply, seconds = ask_model(model, item["text"], item["reply_lang"])
            time.sleep(args.delay)

            # Check A: is the reply really in the requested language?
            reply_language = detect_language(reply).reply_language or "english"
            row = {
                "model": model, "id": item["id"], "type": item["type"],
                "text": item["text"], "expected_reply_lang": item["reply_lang"],
                "reply": reply, "reply_language_detected": reply_language,
                "language_ok": reply_language == item["reply_lang"], "seconds": seconds,
                "understanding": None, "language_quality": None, "comment": "",
            }

            # Check B: AI judge scores.
            if use_judge:
                scores = judge(item, reply, args.judge)
                row["understanding"] = scores.get("understanding")
                row["language_quality"] = scores.get("language_quality")
                row["comment"] = scores.get("comment", "")
                time.sleep(args.delay)

            rows.append(row)
            print(f"  [{number}/{len(eval_set)}] #{item['id']} lang_ok={row['language_ok']} "
                  f"understanding={row['understanding']} quality={row['language_quality']}")

    # Save everything so you can open it in Excel / VS Code afterwards.
    save_json(rows, RESULTS_DIR / "model_comparison.json")
    with open(RESULTS_DIR / "model_comparison.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print_summary(rows, args.models, use_judge)
    print(f"\nFull details saved to {RESULTS_DIR / 'model_comparison.csv'} (open in Excel)")
    print("TIP: read some replies yourself too - an AI judge is helpful but not perfect.")


if __name__ == "__main__":
    main()
