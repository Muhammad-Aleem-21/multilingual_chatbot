"""
chatbot.py  -  puts everything together.

For every user message the bot does 4 things:

    1. DETECT   which language should I reply in?   (language_detect.py)
    2. RETRIEVE which document paragraphs help?      (retrieval.py, optional)
    3. PROMPT   build the instructions for the AI    (build_system_prompt below)
    4. ASK      send it to Groq and return the reply (llm.py)

A "system prompt" is a hidden instruction message that tells the AI who it is and
how to behave. We rebuild it for every message, with the CURRENT reply language,
so the AI never forgets which language to use.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from chatbot import llm
from chatbot.config import DEFAULT_MODEL
from chatbot.language_detect import Detection, LanguageTracker, detect_language

# What to tell the AI for each reply language.
LANGUAGE_INSTRUCTIONS = {
    "english": "Reply in clear, simple English only.",
    "urdu": (
        "Reply ONLY in Urdu, written in Urdu script (اردو). Do not use Roman Urdu and do "
        "not use Hindi/Devanagari. Everyday English shop words (like 'order' or 'refund') "
        "may stay in English letters."
    ),
    "roman_urdu": (
        "Reply ONLY in Roman Urdu: Urdu written with English letters, the way people text "
        "on WhatsApp, for example 'Aapka order 2 se 3 din mein pohanch jayega'. Do not use "
        "Urdu script. Use Urdu words (shukriya, maaf kijiye), not Hindi words "
        "(dhanyavaad, kshama)."
    ),
}

# WHO the bot is. The web page switches to ROLE_DOCUMENTS when the user uploads own files.
ROLE_SHOP = "You are a friendly customer-support assistant for DesiMart, an online store in Pakistan."
ROLE_DOCUMENTS = "You are a helpful assistant that answers questions about the documents the user provided."

SYSTEM_PROMPT = """{role}

Users may write in English, Urdu script, Roman Urdu (Urdu typed in English letters) or a mix of these.
Roman Urdu spelling varies a lot ("kya" = "kia", "hai" = "hy", "haal" = "hal"); understand all variants.

LANGUAGE RULE (very important): {language_instruction}

Keep answers short: 2 to 4 sentences. Be polite and natural.
{context_rules}"""

CONTEXT_RULES_WITH_DOCS = """
Use ONLY the information in the DOCUMENTS below to answer. The documents may be in a different
language than the reply language; translate the facts into the reply language. If the answer is
not in the documents, say you could not find it in the documents (for shop questions, also
suggest contacting customer support). Never invent prices, phone numbers, days, names or policies.

DOCUMENTS:
{documents}"""

CONTEXT_RULES_NO_DOCS = """
You have no shop documents. For specific policies, prices or order details you cannot know,
say so politely and suggest contacting customer support. Never invent facts."""

# Documents ARE switched on, but the search found nothing close to the question.
CONTEXT_RULES_NOTHING_FOUND = """
The documents were searched but nothing relevant to this question was found. Say politely that
you could not find this in the documents, and suggest rephrasing the question or contacting
customer support. Never invent facts."""


def build_system_prompt(language: str, chunks: Optional[list] = None, role: str = ROLE_SHOP,
                        searched: bool = False) -> str:
    """Create the hidden instruction message for ONE turn.

    searched  True when document search was switched on (so "found nothing" is different
              from "there are no documents at all").
    """
    if chunks:
        documents = "\n".join(f"- {chunk.text}" for chunk in chunks)
        context_rules = CONTEXT_RULES_WITH_DOCS.format(documents=documents)
    elif searched:
        context_rules = CONTEXT_RULES_NOTHING_FOUND
    else:
        context_rules = CONTEXT_RULES_NO_DOCS
    return SYSTEM_PROMPT.format(
        role=role, language_instruction=LANGUAGE_INSTRUCTIONS[language], context_rules=context_rules
    )


@dataclass
class BotReply:
    text: str                       # what the bot says
    language: str                   # language the bot was told to use
    detection: Detection            # what the detector saw in the user's message
    sources: List[str] = field(default_factory=list)   # document files that were used
    search_queries: List[str] = field(default_factory=list)  # what was searched (question [+ English])
    translation_error: str = ""     # why the English translation failed ("" = fine / not needed)


class Chatbot:
    def __init__(self, model: str = DEFAULT_MODEL, retriever=None, max_history_turns: int = 6):
        self.model = model
        self.role = ROLE_SHOP               # who the bot pretends to be (see ROLE_* above)
        self.retriever = retriever          # None = chat without documents
        self.tracker = LanguageTracker()    # remembers the language across the chat
        self.history: list = []             # earlier messages, so the bot remembers context
        self.max_history_turns = max_history_turns

    def reset(self) -> None:
        """Start a fresh conversation."""
        self.history = []
        self.tracker = LanguageTracker()

    def reply(self, user_text: str) -> BotReply:
        # 1) which language?
        language = self.tracker.update(user_text)
        detection = detect_language(user_text)

        # 2) which documents? (only if a retriever was given)
        chunks = self.retriever.search(user_text) if self.retriever else []

        # 3) build the messages list: instructions + recent history + new question
        system_prompt = build_system_prompt(language, chunks, self.role,
                                            searched=self.retriever is not None)
        messages = [{"role": "system", "content": system_prompt}]
        messages += self.history[-self.max_history_turns * 2:]
        messages.append({"role": "user", "content": user_text})

        # 4) ask Groq
        answer = llm.chat(messages, model=self.model)

        # remember this exchange for next time
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": answer})

        sources = sorted({chunk.source for chunk in chunks})
        return BotReply(
            text=answer, language=language, detection=detection, sources=sources,
            search_queries=list(getattr(self.retriever, "last_queries", [])),
            translation_error=getattr(self.retriever, "last_translation_error", ""),
        )