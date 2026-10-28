"""
llm.py  -  the ONLY file that talks to Groq.

Keeping all API calls in one place means:
  * the rest of the project just calls  chat(...)  and gets text back,
  * if you ever switch from Groq to another provider, you change only this file.

What is Groq?  A company that runs open AI models (Llama, GPT-OSS ...) very fast
in the cloud. You send a list of messages, it sends back the model's reply.
"""

import time

from groq import APIError, Groq, RateLimitError

from chatbot.config import GROQ_API_KEY

_client = None   # the Groq connection is created once, on first use


class LLMError(Exception):
    """Raised when we cannot get an answer from Groq (a friendly error message)."""


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not GROQ_API_KEY or GROQ_API_KEY == "paste_your_key_here":
            raise LLMError(
                "No Groq API key found. Copy .env.example to .env and put your "
                "key after GROQ_API_KEY="
            )
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def chat(
    messages: list,
    model: str,
    temperature: float = 0.3,
    max_tokens: int = 600,
    json_mode: bool = False,
    retries: int = 4,
) -> str:
    """Send `messages` to `model` and return the reply text.

    messages     list like [{"role": "system", "content": "..."},
                            {"role": "user",   "content": "..."}]
    temperature  0 = very predictable, 1 = more creative.
    json_mode    ask the model to answer with valid JSON only (used by the judge).
    retries      the free Groq plan has speed limits; if we hit one we wait and retry.
    """
    client = _get_client()
    options = dict(model=model, messages=messages, temperature=temperature, max_tokens=max_tokens)
    if json_mode:
        options["response_format"] = {"type": "json_object"}

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(**options)
            return (response.choices[0].message.content or "").strip()
        except RateLimitError:
            wait = 5 * (2 ** attempt)   # 5s, 10s, 20s, 40s
            print(f"  (Groq rate limit - waiting {wait}s and trying again)")
            time.sleep(wait)
        except APIError as error:
            raise LLMError(f"Groq error with model '{model}': {error}") from error

    raise LLMError("Groq rate limit kept failing. Wait a minute and run again.")
