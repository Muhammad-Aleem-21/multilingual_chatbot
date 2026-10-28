"""
config.py  -  ALL the settings of the project live in this one file.

Why a config file?
    If you want to change a model name or a folder, you change it HERE once,
    instead of hunting through many files.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# 1) Folders
# ---------------------------------------------------------------------------
# __file__ is the path of this file (chatbot/config.py).
# .parent is "chatbot/", .parent.parent is the project root folder.
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"          # the English documents the bot searches
RESULTS_DIR = ROOT_DIR / "results"    # evaluation outputs get saved here
EVAL_SET_PATH = DATA_DIR / "eval_set.json"
RETRIEVAL_EVAL_PATH = DATA_DIR / "retrieval_eval.json"

# ---------------------------------------------------------------------------
# 2) API key
# ---------------------------------------------------------------------------
# load_dotenv() reads the file called ".env" and puts its lines into the
# environment, so os.getenv("GROQ_API_KEY") can find your key.
# The key is NEVER written inside the code.
load_dotenv(ROOT_DIR / ".env")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ---------------------------------------------------------------------------
# 3) Models  (names must match what Groq offers - see `python list_models.py`)
# ---------------------------------------------------------------------------
# The model the chatbot uses when you chat with it.
DEFAULT_MODEL = "openai/gpt-oss-20b"

# The two (or more) models we COMPARE in evaluation/compare_models.py.
# "big" model vs "small" model is an easy, meaningful comparison.
MODELS_TO_COMPARE = [
    "qwen/qwen3.8-27b",   # bigger, usually better quality
    "openai/gpt-oss-20b",      # smaller, faster
]

# A third model that acts as the "judge" that scores the answers.
# It is different from the two compared models so it is not grading itself.
JUDGE_MODEL = "openai/gpt-oss-120b"

# ---------------------------------------------------------------------------
# 4) Retrieval (searching the documents)
# ---------------------------------------------------------------------------
# This model turns text into numbers ("embeddings"). It was trained on 50+
# languages including Urdu, so an Urdu question can find an English paragraph.
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
TOP_K = 3   # how many paragraphs to fetch for each question
# Paragraphs scoring below this (0 = unrelated, 1 = identical meaning) are ignored,
# so small talk like "assalamualaikum" does not drag in random documents.
MIN_SCORE = 0.25

# ---------------------------------------------------------------------------
# 5) Language handling
# ---------------------------------------------------------------------------
# In a mixed message, if at least this share of the recognised words are
# Urdu / Roman Urdu, we reply in that language; otherwise we reply in English.
LOCAL_SHARE_THRESHOLD = 0.4

LANGUAGES = ("english", "urdu", "roman_urdu")
DEFAULT_LANGUAGE = "english"   # used when we cannot tell (e.g. just "ok")
