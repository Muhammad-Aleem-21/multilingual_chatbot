"""
eval_retrieval.py  -  does an Urdu question find the right ENGLISH document?

data/retrieval_eval.json contains questions (Urdu script, Roman Urdu, English) and
the document file that SHOULD be found for each. We test two strategies:

    A) "direct"     embed the question as it is and search.
    B) "translate"  first translate the question to English with Groq, then search.
                    (needs your Groq key; skipped if no key)

Metrics:
    hit@1   the correct document is the TOP result.
    hit@3   the correct document is among the top 3 results.

Run:   python -m evaluation.eval_retrieval
(first run downloads the ~470 MB embedding model)
"""

import time

from chatbot.config import RESULTS_DIR, RETRIEVAL_EVAL_PATH, TOP_K
from chatbot.llm import LLMError
from chatbot.retrieval import Retriever
from evaluation.common import group_by, load_json, percent, save_json


def evaluate(retriever: Retriever, queries: list, label: str) -> list:
    """Run every query through the retriever and record whether it found the right file."""
    rows = []
    for item in queries:
        # min_score=-1 so we always get TOP_K results to judge ranking fairly.
        results = retriever.search(item["query"], k=TOP_K, min_score=-1)
        ranked_sources = []
        for chunk in results:                     # several chunks can come from one file;
            if chunk.source not in ranked_sources:   # keep each file once, in rank order
                ranked_sources.append(chunk.source)
        expected = item["expected_source"]
        rows.append({
            "strategy": label, "id": item["id"], "type": item["type"], "query": item["query"],
            "expected": expected, "top_files": ranked_sources,
            "hit_at_1": bool(ranked_sources) and ranked_sources[0] == expected,
            "hit_at_3": expected in ranked_sources[:3],
        })
        if retriever.use_query_translation:
            time.sleep(1)   # be gentle with Groq's rate limit
    return rows


def report(rows: list, label: str) -> None:
    print(f"\nStrategy: {label}")
    print(f"  {'type':<12}{'hit@1':>9}{'hit@3':>9}{'questions':>11}")
    for type_name, group in sorted(group_by(rows, "type").items()):
        h1 = sum(r["hit_at_1"] for r in group)
        h3 = sum(r["hit_at_3"] for r in group)
        print(f"  {type_name:<12}{percent(h1, len(group)):>9}{percent(h3, len(group)):>9}{len(group):>11}")
    h1 = sum(r["hit_at_1"] for r in rows)
    h3 = sum(r["hit_at_3"] for r in rows)
    print(f"  {'ALL':<12}{percent(h1, len(rows)):>9}{percent(h3, len(rows)):>9}{len(rows):>11}")
    for r in rows:
        if not r["hit_at_1"]:
            print(f"    miss: {r['query']}  -> expected {r['expected']}, got {r['top_files']}")


def main() -> None:
    queries = load_json(RETRIEVAL_EVAL_PATH)
    print(f"{len(queries)} test questions loaded.")

    all_rows = []

    direct = Retriever(use_query_translation=False)
    rows = evaluate(direct, queries, "direct (no translation)")
    report(rows, "direct (no translation)")
    all_rows += rows

    # Reuse the already-loaded embedding model: just flip the switch.
    direct.use_query_translation = True
    try:
        rows = evaluate(direct, queries, "translate-then-search")
        report(rows, "translate-then-search")
        all_rows += rows
    except LLMError as error:
        print(f"\nSkipped translate-then-search: {error}")

    save_json(all_rows, RESULTS_DIR / "retrieval_eval.json")
    print(f"\nSaved details to {RESULTS_DIR / 'retrieval_eval.json'}")


if __name__ == "__main__":
    main()
