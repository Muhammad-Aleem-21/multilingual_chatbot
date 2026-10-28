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
from chatbot.config import DEFAULT_MODEL, DOCS_DIR, EMBEDDING_MODEL, MIN_SCORE, TOP_K
from chatbot.language_detect import detect_language
from chatbot.llm import LLMError

# The embedding model only "reads" about 128 word-pieces, so chunks must stay short.
MAX_CHUNK_CHARS = 500


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

    def with_documents(self, chunks: List[Chunk]) -> "Retriever":
        """A NEW Retriever over different chunks, re-using the already-loaded model."""
        return Retriever(chunks=chunks, model=self.model,
                         use_query_translation=self.use_query_translation,
                         translate_model=self.translate_model)

    def translate_query(self, query: str) -> str:
        """Ask the LLM to turn an Urdu / Roman Urdu / mixed question into English."""
        messages = [
            {"role": "system", "content": (
                "Translate the user's message into plain English. The message may be Urdu "
                "script, Roman Urdu (Urdu in English letters, with spelling variations) or a "
                "mix with English. Output ONLY the English translation, nothing else.")},
            {"role": "user", "content": query},
        ]
        return llm.chat(messages, model=self.translate_model, temperature=0, max_tokens=120)

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
        if self.use_query_translation and detect_language(query).reply_language in ("urdu", "roman_urdu"):
            try:
                english = self.translate_query(query).strip()
            except LLMError:
                english = ""               # translation failed: just search with the original
            if english and english.lower() != query.strip().lower():
                queries.append(english)
        return queries

    def search(self, query: str, k: int = TOP_K, min_score: float = MIN_SCORE) -> List[Chunk]:
        """Return up to k chunks that best match the query's meaning."""
        # For every chunk keep its BEST score over all the query versions.
        scores = np.max([self.score_all(text) for text in self.queries_for(query)], axis=0)
        best_first = np.argsort(-scores)[:k]           # indexes of the k highest scores

        results = []
        for index in best_first:
            if scores[index] >= min_score:
                chunk = self.chunks[index]
                results.append(Chunk(chunk.text, chunk.source, float(scores[index])))
        return results