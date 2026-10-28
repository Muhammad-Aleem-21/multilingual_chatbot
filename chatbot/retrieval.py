"""
retrieval.py  -  "find the right paragraph in the documents"  (cross-language search)

THE PROBLEM
    Our documents are in English, but users ask in Urdu / Roman Urdu.
    A normal keyword search fails: the Urdu word "ڈیلیوری" never matches "delivery".

THE SOLUTION: EMBEDDINGS
    An embedding model turns a sentence into a list of numbers (a "vector") that
    captures its MEANING. Sentences with similar meaning get similar numbers -
    even across languages. We use a multilingual model, so:

        "ڈیلیوری میں کتنے دن لگتے ہیں؟"   (Urdu question)
        "Orders in major cities arrive in 2 to 3 working days"   (English text)

    end up close together. Searching = comparing numbers, not words.

WHAT THIS FILE DOES
    1. load_chunks()        reads data/docs/*.txt and cuts them into paragraphs ("chunks").
       chunks_from_files()  does the same for files a user UPLOADS (txt, md, pdf).
    2. Retriever            turns every chunk into a vector once.
    3. search()             turns the question into a vector, then returns the chunks
                            whose vectors are closest ("cosine similarity").

ROMAN URDU EXTRA
    The embedding model has seen real Urdu script, but very little Roman Urdu.
    So there is an optional trick, use_query_translation=True: first ask the
    Groq model to translate the question into English, then search with that.
    evaluation/eval_retrieval.py measures whether the trick helps.
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import numpy as np

from chatbot import llm
from chatbot.config import (DEFAULT_MODEL, DOCS_DIR, EMBEDDING_MODEL, MIN_SCORE,
                            MODELS_TO_COMPARE, TOP_K)
from chatbot.language_detect import detect_language
from chatbot.llm import LLMError

# The embedding model only "reads" about 128 word-pieces, so chunks must stay short.
MAX_CHUNK_CHARS = 500

# A document at most this long (in characters) is given to the AI WHOLE when it matches.
DOC_EXPAND_MAX_CHARS = 3000


@dataclass
class Chunk:
    text: str          # the paragraph (with its document title in front)
    source: str        # file name it came from, e.g. "delivery.txt"
    score: float = 0.0  # similarity to the question (filled in by search)


# ---------------------------------------------------------------------------
# Reading + cutting documents into chunks
# ---------------------------------------------------------------------------
def load_chunks(docs_dir: Path = DOCS_DIR) -> List[Chunk]:
    """Read every .txt file. First line = title, then paragraphs split by blank lines."""
    chunks = []
    for path in sorted(Path(docs_dir).glob("*.txt")):
        text = path.read_text(encoding="utf-8").strip()
        title, *paragraphs = [part.strip() for part in text.split("\n\n")]
        for paragraph in paragraphs:
            if paragraph:
                chunks.append(Chunk(text=f"{title}: {paragraph}", source=path.name))
    return chunks


def _split_long(paragraph: str, max_chars: int) -> List[str]:
    """Cut a long paragraph into pieces of at most max_chars, at sentence ends if possible."""
    sentences = re.split(r"(?<=[.!?۔؟])\s+", paragraph)    # the signs include Urdu full stop / ?
    pieces, current = [], ""
    for sentence in sentences:
        while len(sentence) > max_chars:                    # one giant "sentence": cut hard
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, source: str, max_chars: int = MAX_CHUNK_CHARS) -> List[Chunk]:
    """Cut ANY text (an uploaded file) into short chunks. No special format needed."""
    chunks = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = " ".join(paragraph.split())            # tidy line breaks and spaces
        if not paragraph:
            continue
        pieces = [paragraph] if len(paragraph) <= max_chars else _split_long(paragraph, max_chars)
        for piece in pieces:
            chunks.append(Chunk(text=f"{source}: {piece}", source=source))
    return chunks


def read_document(name: str, data: bytes) -> str:
    """Turn an uploaded file (its name + raw bytes) into plain text."""
    lower = name.lower()
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise RuntimeError("PDF files need one more package: pip install pypdf") from error
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if lower.endswith((".txt", ".md")):
        return data.decode("utf-8-sig", errors="replace")
    raise RuntimeError(f"Unsupported file type: {name} (use .txt, .md or .pdf)")


def chunks_from_files(files: List[Tuple[str, bytes]]) -> Tuple[List[Chunk], List[str]]:
    """files = [(name, bytes), ...]. Returns (all chunks, list of problems to show the user)."""
    chunks, problems = [], []
    for name, data in files:
        try:
            new_chunks = chunk_text(read_document(name, data), name)
        except Exception as error:                          # show the problem, keep going
            problems.append(f"{name}: {error}")
            continue
        if not new_chunks:
            problems.append(f"{name}: no readable text found (a scanned PDF has only pictures)")
        chunks += new_chunks
    return chunks, problems


def clean_translation(raw: str) -> str:
    """Tidy a model's translation: drop hidden <think>...</think> reasoning and quotes."""
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    if "<think>" in text:                    # reasoning started but never finished = unusable
        return ""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[0].strip(" \"'“”") if lines else ""


# ---------------------------------------------------------------------------
# The searcher
# ---------------------------------------------------------------------------
class Retriever:
    def __init__(self, docs_dir: Path = DOCS_DIR, use_query_translation: bool = True,
                 translate_model: str = DEFAULT_MODEL, chunks=None, model=None):
        """
        use_query_translation  True (default): Urdu / Roman Urdu questions are ALSO searched
                 with an English translation (see queries_for). False = search as typed.
        chunks   give your own list of Chunk objects (e.g. from uploaded files);
                 otherwise the .txt files in docs_dir are used.
        model    an already-loaded embedding model to reuse (loading takes a while).
        """
        if model is None:
            # Imported here (not at the top) so the rest of the project still works
            # even if sentence-transformers is not installed yet.
            from sentence_transformers import SentenceTransformer

            print(f"Loading embedding model '{EMBEDDING_MODEL}' (first time downloads ~470 MB)...")
            model = SentenceTransformer(EMBEDDING_MODEL)
        self.model = model
        self.chunks = chunks if chunks is not None else load_chunks(docs_dir)
        if not self.chunks:
            raise ValueError(f"No documents found in {docs_dir}")

        # One vector per chunk. normalize_embeddings=True makes every vector length 1,
        # so a simple dot product equals cosine similarity.
        self.vectors = self.model.encode(
            [chunk.text for chunk in self.chunks], normalize_embeddings=True
        )
        self.use_query_translation = use_query_translation
        self.translate_model = translate_model
        # Models tried (in this order) for translating a question: the chosen one first, then
        # the other models from config.py as a backup.
        self.translate_models = list(dict.fromkeys([translate_model] + list(MODELS_TO_COMPARE)))
        self.last_queries = []              # what the last search used (question [+ translation])
        self.last_translation_error = ""    # why translation failed, "" if it did not

        # Bookkeeping used by search(): which chunks belong to which document, and how
        # long each document is.
        self.source_members = {}   # "return_policy.txt" -> [chunk numbers, in order]
        self.source_chars = {}     # "return_policy.txt" -> total characters
        for number, chunk in enumerate(self.chunks):
            self.source_members.setdefault(chunk.source, []).append(number)
            self.source_chars[chunk.source] = self.source_chars.get(chunk.source, 0) + len(chunk.text)

    def with_documents(self, chunks: List[Chunk]) -> "Retriever":
        """A NEW Retriever over different chunks, re-using the already-loaded model."""
        return Retriever(chunks=chunks, model=self.model,
                         use_query_translation=self.use_query_translation,
                         translate_model=self.translate_model)

    def translate_query(self, query: str) -> str:
        """Ask the LLM to turn an Urdu / Roman Urdu / mixed question into English.

        Returns "" if no model could do it; the reason is then in self.last_translation_error
        (so the page and check_retrieval.py can SHOW why instead of failing silently).
        """
        messages = [
            {"role": "system", "content": (
                "You translate customer messages into a short, clear English question or "
                "sentence. The message may be Urdu script, Roman Urdu (Urdu typed in English "
                "letters, with creative spelling and typos, e.g. 'cheex kitne din k ander wapsi "
                "ho skti h' = 'within how many days can an item be returned') or a mix with "
                "English. Output ONLY the English translation, nothing else.")},
            {"role": "user", "content": query},
        ]
        problems = []
        for model in self.translate_models:             # try the next model if one fails
            try:
                # Generous token limit: "thinking" models (gpt-oss, qwen3 ...) spend tokens
                # on hidden reasoning first and return NOTHING if the limit is too small.
                raw = llm.chat(messages, model=model, temperature=0, max_tokens=1500)
            except LLMError as error:
                problems.append(f"{model}: {error}")
                continue
            text = clean_translation(raw)
            if text:
                self.last_translation_error = ""
                return text
            problems.append(f"{model}: returned an empty answer")
        self.last_translation_error = " | ".join(problems)
        return ""

    def score_all(self, query: str) -> np.ndarray:
        """Similarity (0..1, higher = closer in meaning) between the query and EVERY chunk."""
        query_vector = self.model.encode([query], normalize_embeddings=True)[0]
        return self.vectors @ query_vector

    def queries_for(self, query: str) -> List[str]:
        """The texts we search with: the question itself, plus an English translation of it.

        Why both? The embedding model understands Urdu script reasonably, but similarity
        scores between an Urdu question and an English paragraph come out LOWER than
        English-to-English, and Roman Urdu is understood even less. An English translation
        of the question matches an English document much more strongly. Using the best
        score of the two means the translation can only help, never hurt.
        English questions are never translated (saves a Groq call).
        """
        queries = [query]
        self.last_translation_error = ""
        if self.use_query_translation and detect_language(query).reply_language in ("urdu", "roman_urdu"):
            english = self.translate_query(query)   # "" when it failed (reason saved)
            if english and english.lower() != query.strip().lower():
                queries.append(english)
        self.last_queries = queries                 # so the page can show what was searched
        return queries

    def search(self, query: str, k: int = TOP_K, min_score: float = MIN_SCORE) -> List[Chunk]:
        """Return the chunks that best match the query's meaning.

        Step 1  score every chunk and keep the k best that reach min_score  ("hits").
        Step 2  EXPAND each hit so the AI sees the whole story, not a random slice:
                  - SHORT document (<= DOC_EXPAND_MAX_CHARS): include ALL its chunks.
                  - LONG document (e.g. a big PDF): include the hit plus its neighbours
                    (one chunk before and after).
        Why? Paragraphs of one document often score almost the same, so the "top 3" can
        silently drop the one that holds the answer (for example the paragraph that says
        "return within 7 days"). Expanding fixes that.
        """
        # For every chunk keep its BEST score over all the query versions.
        scores = np.max([self.score_all(text) for text in self.queries_for(query)], axis=0)
        best_first = np.argsort(-scores)[:k]           # indexes of the k highest scores
        hits = [int(i) for i in best_first if scores[i] >= min_score]

        wanted = set()                                  # chunk numbers we will return
        group_best = {}                                 # best score per document (for ordering)
        for index in hits:
            source = self.chunks[index].source
            group_best[source] = max(group_best.get(source, -1.0), float(scores[index]))
            members = self.source_members[source]       # chunk numbers of this document, in order
            if self.source_chars[source] <= DOC_EXPAND_MAX_CHARS:
                wanted.update(members)
            else:
                position = members.index(index)
                wanted.update(members[max(0, position - 1): position + 2])

        # Best document first; inside a document keep the original reading order.
        ordered = sorted(wanted, key=lambda i: (-group_best[self.chunks[i].source], i))
        return [Chunk(self.chunks[i].text, self.chunks[i].source, float(scores[i])) for i in ordered]