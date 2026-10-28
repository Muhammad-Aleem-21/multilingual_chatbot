"""
app_web.py  -  a chat WEB PAGE for the bot (uses Streamlit).

Two modes (choose in the sidebar):
    Chat                 normal conversation with ONE model
    Compare two models   one question goes to TWO models; answers appear side by side,
                         with scores (out of 10) from an AI judge and extra measurements

Documents: tick "Answer from documents", then use either the built-in shop documents
(data/docs) or UPLOAD your own files (.txt, .md, .pdf).

Run it from the project folder (with your .venv switched on):

    streamlit run app_web.py

A browser tab opens at http://localhost:8501 . Stop it with Ctrl+C in the terminal.

HOW STREAMLIT WORKS (the one idea you need)
    Streamlit runs this whole file from top to bottom EVERY time you click or type.
    Anything that must survive between runs (the chat history, the bot) is stored in
    `st.session_state`, a dictionary that Streamlit keeps for you.
"""

import hashlib
import html
import json
import random
import re
import time

import streamlit as st

from chatbot import llm
from chatbot.chatbot import ROLE_DOCUMENTS, ROLE_SHOP, Chatbot, build_system_prompt
from chatbot.config import DEFAULT_MODEL, JUDGE_MODEL, MODELS_TO_COMPARE
from chatbot.language_detect import LanguageTracker, detect_language
from chatbot.llm import LLMError
from chatbot.retrieval import chunks_from_files

st.set_page_config(page_title="DesiMart Assistant", page_icon="🛒", layout="wide")

URDU_LETTERS = re.compile(r"[\u0600-\u06FF]")
LANGUAGE_LABELS = {"english": "English", "urdu": "Urdu", "roman_urdu": "Roman Urdu"}

BUILT_IN = "Built-in shop documents"
UPLOAD = "Upload my own files"

# (text shown on the page, key used in the judge's JSON answer)
SCORE_ROWS = [
    ("Understanding of the question", "understanding"),
    ("Language quality", "language_quality"),
    ("Helpfulness", "helpfulness"),
    ("Grounded in documents", "grounded"),
]


# ---------------------------------------------------------------------------
# Documents (search index)
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading the document-search model (first time takes a while)...")
def load_retriever():
    """Create the Retriever ONCE and reuse it. cache_resource = 'remember this object'."""
    from chatbot.retrieval import Retriever   # imported here because it is heavy
    return Retriever()


def retriever_for_uploads(base, uploaded_files):
    """Build (or re-use) a search index made from the files the user uploaded."""
    files = [(f.name, f.getvalue()) for f in uploaded_files]
    # A "fingerprint" of the files: if it did not change, we do not rebuild the index.
    key = tuple((name, hashlib.md5(data).hexdigest()) for name, data in files)
    cached = st.session_state.get("upload_index")
    if cached and cached[0] == key:
        return cached[1]

    with st.spinner("Reading your files and building the search index..."):
        chunks, problems = chunks_from_files(files)
        for problem in problems:
            st.sidebar.warning(problem)
        if not chunks:
            return None
        retriever = base.with_documents(chunks)
    st.session_state.upload_index = (key, retriever)
    st.sidebar.success(f"Ready: {len(chunks)} text pieces from {len(files)} file(s)")
    return retriever


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def show_text(text: str) -> None:
    """Draw text. Urdu text is shown right-to-left."""
    if URDU_LETTERS.search(text):
        safe = html.escape(text).replace("\n", "<br>")
        st.markdown(
            f'<div dir="rtl" style="text-align:right; font-size:1.1em;">{safe}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(text)


def show_message(role: str, text: str, caption: str = "") -> None:
    """Draw one chat bubble."""
    with st.chat_message(role):
        show_text(text)
        if caption:
            st.caption(caption)


def new_chat() -> None:
    st.session_state.messages = []       # chat mode: what is drawn on the page
    st.session_state.comparisons = []    # compare mode: all questions asked so far
    st.session_state.bot = Chatbot()     # a fresh bot (fresh memory + language tracker)


def number(value):
    """Format a score: 8.0 -> '8', None -> a dash."""
    return "–" if value is None else f"{value:g}"


# ---------------------------------------------------------------------------
# The AI judge (used only in "Compare two models" mode)
# ---------------------------------------------------------------------------
JUDGE_SYSTEM = """You are a strict but fair evaluator of a multilingual chatbot. Users write in English,
Urdu script, Roman Urdu (Urdu typed in English letters, with varied spelling) or a mix.
You will see one user message and two replies, REPLY X and REPLY Y, from two different models.
Score EACH reply from 0 (terrible) to 10 (excellent):

- understanding: did the reply show the model truly understood what the user meant and asked?
- language_quality: natural, correct writing in the REQUIRED reply language and script. A reply in
  the wrong language or script must get a low score.
- helpfulness: does it actually help the user, clearly and politely?
- grounded: ONLY if documents were given: are the reply's facts supported by the documents and not
  invented? If no documents were given, use null.

Also write, for each reply:
- understood_as: one short English sentence: what the reply suggests the model thought the user wanted.
- strengths: max 12 words.
- weaknesses: max 12 words.

Do not prefer a reply because it is longer or because of its position.
Answer with JSON only, exactly in this shape:
{"user_meaning": "<what the user means, in English>",
 "X": {"understanding": 0, "language_quality": 0, "helpfulness": 0, "grounded": null,
       "understood_as": "", "strengths": "", "weaknesses": ""},
 "Y": {"understanding": 0, "language_quality": 0, "helpfulness": 0, "grounded": null,
       "understood_as": "", "strengths": "", "weaknesses": ""},
 "better": "X" or "Y" or "tie",
 "reason": "<max 20 words>"}"""


def parse_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)   # JSON hidden inside extra text
        if match:
            return json.loads(match.group(0))
        raise


def clean_scores(data: dict) -> dict:
    """Make the judge's answer safe: numbers between 0 and 10, plus the overall average."""
    out = {}
    for _, key in SCORE_ROWS:
        value = data.get(key)
        out[key] = max(0.0, min(10.0, float(value))) if isinstance(value, (int, float)) else None
    numbers = [v for v in out.values() if v is not None]
    out["overall"] = round(sum(numbers) / len(numbers), 1) if numbers else None
    for key in ("understood_as", "strengths", "weaknesses"):
        out[key] = str(data.get(key, "")).strip()
    return out


def judge_replies(question: str, language: str, chunks: list, replies: list, judge_model: str) -> dict:
    """Ask the judge to score both replies. Returns scores per reply (same order as `replies`)."""
    # Shuffle which reply is called X and which Y, so the judge cannot favour "the first one".
    order = [0, 1]
    random.shuffle(order)
    shown = {"X": replies[order[0]], "Y": replies[order[1]]}
    documents = "\n".join(f"- {chunk.text}" for chunk in chunks) or "(no documents were given)"
    prompt = (
        f"USER MESSAGE:\n{question}\n\n"
        f"REQUIRED REPLY LANGUAGE: {LANGUAGE_LABELS[language]}\n\n"
        f"DOCUMENTS GIVEN TO THE BOTS:\n{documents}\n\n"
        f"REPLY X:\n{shown['X']}\n\nREPLY Y:\n{shown['Y']}"
    )
    raw = llm.chat(
        [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": prompt}],
        model=judge_model, temperature=0, max_tokens=2000, json_mode=True,
    )
    data = parse_json(raw)

    scores = [None, None]
    scores[order[0]] = clean_scores(data.get("X", {}))   # put the scores back in the ORIGINAL order
    scores[order[1]] = clean_scores(data.get("Y", {}))
    winner = None                                        # 0 = model A, 1 = model B, -1 = tie
    if data.get("better") in ("X", "Y"):
        winner = order[0] if data["better"] == "X" else order[1]
    elif data.get("better") == "tie":
        winner = -1
    return {"scores": scores, "winner": winner, "user_meaning": str(data.get("user_meaning", "")),
            "reason": str(data.get("reason", "")), "judge_model": judge_model}


# ---------------------------------------------------------------------------
# Compare mode
# ---------------------------------------------------------------------------
def run_comparison(question, model_a, model_b, retriever, role, judge_model) -> dict:
    """Send the SAME question (same instructions, same documents) to both models, then judge."""
    language = LanguageTracker().update(question)
    chunks = retriever.search(question) if retriever else []
    messages = [
        {"role": "system", "content": build_system_prompt(language, chunks, role)},
        {"role": "user", "content": question},
    ]
    results = []
    for model in (model_a, model_b):
        start = time.time()
        try:
            text, error = llm.chat(messages, model=model), False
        except LLMError as problem:
            text, error = str(problem), True
        results.append({
            "model": model, "text": text, "error": error,
            "seconds": round(time.time() - start, 1),
            "words": len(text.split()),
            "reply_language": None if error else detect_language(text).reply_language,
        })

    entry = {"question": question, "language": language, "judge": None, "judge_error": "",
             "sources": sorted({chunk.source for chunk in chunks}), "results": results}
    if judge_model and not any(r["error"] for r in results):
        try:
            entry["judge"] = judge_replies(question, language, chunks,
                                           [r["text"] for r in results], judge_model)
        except (LLMError, ValueError, KeyError, TypeError) as problem:
            entry["judge_error"] = f"The judge could not score this one: {problem}"
    return entry


def show_scores(scores: dict) -> None:
    """Score bars (0-10) for one model."""
    for label, key in SCORE_ROWS:
        value = scores.get(key)
        if value is None:
            continue
        st.markdown(f"{label}: **{number(value)}/10**")
        st.progress(value / 10)
    st.markdown(f"**Overall: {number(scores['overall'])}/10**")


def show_comparison(entry: dict) -> None:
    """Draw one question, the two answers, the scores and the summary table."""
    show_message("user", entry["question"])
    caption = f"Reply language requested: {LANGUAGE_LABELS[entry['language']]}"
    if entry["sources"]:
        caption += f" · documents used: {', '.join(entry['sources'])}"
    st.caption(caption)

    judge = entry["judge"]
    names = [r["model"] for r in entry["results"]]
    if judge:
        st.info(f"**How the judge read the question:** {judge['user_meaning']}")
        if judge["winner"] in (0, 1):
            st.success(f"**Better answer: {names[judge['winner']]}**. {judge['reason']}")
        elif judge["winner"] == -1:
            st.success(f"**It is a tie.** {judge['reason']}")
    elif entry["judge_error"]:
        st.warning(entry["judge_error"])

    columns = st.columns(2)
    for index, (column, result) in enumerate(zip(columns, entry["results"])):
        with column:
            with st.container(border=True):
                st.markdown(f"**Model {'AB'[index]}: {result['model']}**")
                if result["error"]:
                    st.error(result["text"])
                    continue
                show_text(result["text"])
                st.caption(f"⏱ {result['seconds']} s · {result['words']} words")
                if judge:
                    scores = judge["scores"][index]
                    show_scores(scores)
                    st.markdown(f"**Understood the question as:** {scores['understood_as']}")
                    st.markdown(f"👍 {scores['strengths']}")
                    st.markdown(f"👎 {scores['weaknesses']}")

    if judge:
        st.markdown("**Side-by-side summary**")
        labels = [f"A: {names[0]}", f"B: {names[1]}"]
        rows = {
            "Understanding (0-10)": [number(s["understanding"]) for s in judge["scores"]],
            "Language quality (0-10)": [number(s["language_quality"]) for s in judge["scores"]],
            "Helpfulness (0-10)": [number(s["helpfulness"]) for s in judge["scores"]],
            "Grounded in documents (0-10)": [number(s["grounded"]) for s in judge["scores"]],
            "Overall (0-10)": [number(s["overall"]) for s in judge["scores"]],
            "Answered in the requested language": [
                "✅ yes" if r["reply_language"] == entry["language"] else "⚠️ no"
                for r in entry["results"]],
            "Speed (seconds)": [str(r["seconds"]) for r in entry["results"]],
            "Length (words)": [str(r["words"]) for r in entry["results"]],
        }
        # st.table wants {column: {row: value}}
        st.table({labels[i]: {row: values[i] for row, values in rows.items()} for i in range(2)})
        st.caption(f"Scored by {judge['judge_model']}. An AI judge is helpful but not perfect: "
                   "read the answers yourself too.")


# ---------------------------------------------------------------------------
# Sidebar: settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")
    mode = st.radio("Mode", ["Chat", "Compare two models"])
    models = list(dict.fromkeys([DEFAULT_MODEL] + MODELS_TO_COMPARE))   # no duplicates

    judge_model = None
    if mode == "Chat":
        model = st.selectbox("Model", models)
    else:
        model_a = st.selectbox("Model A", models, index=0)
        model_b = st.selectbox("Model B", models, index=min(1, len(models) - 1))
        if st.checkbox("Score the answers with an AI judge", value=True,
                       help="Costs one extra Groq call per question."):
            judge_choices = list(dict.fromkeys([JUDGE_MODEL] + models))
            judge_model = st.selectbox("Judge model", judge_choices)
            if judge_model in (model_a, model_b):
                st.caption("⚠️ The judge is one of the compared models; it may favour itself. "
                           "Pick a different judge if you can.")

    st.divider()
    use_docs = st.checkbox("Answer from documents", value=False,
                           help="The bot searches your documents and answers from them.")
    doc_source = BUILT_IN
    uploaded_files = []
    if use_docs:
        doc_source = st.radio("Which documents?", [BUILT_IN, UPLOAD])
        if doc_source == UPLOAD:
            uploaded_files = st.file_uploader(
                "Upload .txt, .md or .pdf files", type=["txt", "md", "pdf"],
                accept_multiple_files=True,
                help="Files are used only in this session. Scanned PDFs (pictures) cannot be read.",
            )
        translate_first = st.checkbox("Also search with an English translation (recommended)",
                                      value=True,
                                      help="Urdu and Roman Urdu questions find English documents "
                                           "far more reliably this way. Costs one small Groq call.")
    else:
        translate_first = False

    st.divider()
    if st.button("Clear conversation"):
        new_chat()
        st.rerun()
    st.caption("Try: kya hal hai · mera order kahan hai · ڈیلیوری میں کتنے دن لگتے ہیں؟ · "
               "please reply in English")

# ---------------------------------------------------------------------------
# State: create the bot on the first run only, then pick the document source
# ---------------------------------------------------------------------------
if "bot" not in st.session_state:
    new_chat()

retriever = None
role = ROLE_SHOP
if use_docs:
    base = load_retriever()
    if doc_source == UPLOAD:
        role = ROLE_DOCUMENTS
        if uploaded_files:
            retriever = retriever_for_uploads(base, uploaded_files)
    else:
        retriever = base
    if retriever:
        retriever.use_query_translation = translate_first

bot = st.session_state.bot
bot.retriever = retriever
bot.role = role
if mode == "Chat":
    bot.model = model

# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.title("Multilingual chatbot")

if use_docs and doc_source == UPLOAD and retriever is None:
    st.warning("Documents are switched on, but no readable file is uploaded yet "
               "(use the sidebar). Until then the bot answers without documents.")

if mode == "Chat":
    st.write("Ask in **English**, **اردو** or **Roman Urdu**. The bot replies in the same language.")

    # 1) redraw the conversation so far
    for message in st.session_state.messages:
        show_message(message["role"], message["content"], message.get("caption", ""))

    # 2) wait for a new message
    user_text = st.chat_input("Type here... / یہاں لکھیں... / yahan likhein...")
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        show_message("user", user_text)

        try:
            with st.spinner("Thinking..."):
                reply = bot.reply(user_text)
        except LLMError as error:
            st.error(str(error))
        else:
            caption = (f"Detected: {reply.detection.label} → replied in "
                       f"{LANGUAGE_LABELS[reply.language]}")
            if reply.sources:
                caption += f" · documents used: {', '.join(reply.sources)}"
            st.session_state.messages.append(
                {"role": "assistant", "content": reply.text, "caption": caption}
            )
            show_message("assistant", reply.text, caption)

else:
    st.write("Type one question: **both models answer it**, side by side"
             + (", then the judge scores them." if judge_model else "."))
    if model_a == model_b:
        st.warning("Model A and Model B are the same. Pick two different models to compare.")

    for entry in st.session_state.comparisons:
        show_comparison(entry)

    question = st.chat_input("Type a question to send to both models...")
    if question:
        with st.spinner("Asking both models" + (" and the judge..." if judge_model else "...")):
            entry = run_comparison(question, model_a, model_b, retriever, role, judge_model)
        st.session_state.comparisons.append(entry)
        show_comparison(entry)