"""
eval_language_detection.py  -  how good is our language detector?

It runs the detector on every message in data/eval_set.json and compares its
answer with the correct answer ("reply_lang") that a human wrote down.

No internet and no API key needed. Run:

    python -m evaluation.eval_language_detection

Output:
  * overall accuracy and accuracy per message type (english / urdu / roman_urdu / mixed)
  * every mistake, so you can fix word lists in chatbot/language_detect.py
  * a "spelling variation" check: messages with the same meaning but different
    spellings (kya hal hai / kia haal hai) should be treated the same way.
"""

from chatbot.config import EVAL_SET_PATH
from chatbot.language_detect import detect_language
from evaluation.common import group_by, load_json, percent


def main() -> None:
    eval_set = load_json(EVAL_SET_PATH)
    print(f"Loaded {len(eval_set)} messages from {EVAL_SET_PATH.name}\n")

    mistakes = []
    for item in eval_set:
        detection = detect_language(item["text"])
        # If the detector cannot tell, the chatbot falls back to English.
        predicted = detection.reply_language or "english"
        item["predicted"] = predicted
        item["correct"] = predicted == item["reply_lang"]
        if not item["correct"]:
            mistakes.append((item, detection))

    # ---- overall + per type -------------------------------------------------
    total_correct = sum(item["correct"] for item in eval_set)
    print(f"OVERALL reply-language accuracy: {percent(total_correct, len(eval_set))} "
          f"({total_correct}/{len(eval_set)})\n")

    print("By message type:")
    for type_name, rows in sorted(group_by(eval_set, "type").items()):
        right = sum(row["correct"] for row in rows)
        print(f"  {type_name:<11} {percent(right, len(rows))}  ({right}/{len(rows)})")

    # ---- mistakes -----------------------------------------------------------
    print(f"\nMistakes ({len(mistakes)}):")
    for item, detection in mistakes:
        print(f"  #{item['id']:<3} {item['text']}")
        print(f"       expected: {item['reply_lang']:<11} got: {item['predicted']:<11} "
              f"word counts: {detection.counts}")

    # ---- spelling variation check ------------------------------------------
    print("\nSpelling-variation check (same meaning -> same reply language?):")
    inconsistent = 0
    for group_name, rows in sorted(group_by(eval_set, "group").items()):
        # only compare messages that SHOULD get the same reply language
        for language, same in group_by(rows, "reply_lang").items():
            if len(same) < 2:
                continue
            predictions = {row["predicted"] for row in same}
            if len(predictions) > 1:
                inconsistent += 1
                print(f"  group '{group_name}' ({language}): detector disagrees with itself")
    if inconsistent == 0:
        print("  all groups consistent")

    print("\nNOTE: the word lists were improved while looking at this same set, so this score is")
    print("optimistic. Add NEW messages you collect (friends, WhatsApp style) to eval_set.json")
    print("for an honest test.")


if __name__ == "__main__":
    main()
