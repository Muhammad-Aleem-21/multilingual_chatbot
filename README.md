# Roman Urdu & Multilingual Chatbot

A customer-support chatbot for a (fictional) online shop, **DesiMart**. It understands and answers in:

| Style | Example |
|---|---|
| English | `Where is my order?` |
| Urdu script | `میرا آرڈر کہاں ہے؟` |
| Roman Urdu (Urdu typed in English letters) | `mera order kahan hai` |
| Mixed | `Mera order track kar do please` |

## The 4 deliverables and where they live

| Deliverable | Where |
|---|---|
| Language detection + consistent reply language | `chatbot/language_detect.py` |
| Evaluation set (70 messages, spelling variations) | `data/eval_set.json` and `evaluation/eval_language_detection.py` |
| Comparison of 2 models on local-language input | `evaluation/compare_models.py` |
| Retrieval across languages (Urdu question → English document) | `chatbot/retrieval.py` and `evaluation/eval_retrieval.py` |

---

## 1. Setup in VS Code (once)

1. Install **Python 3.10 or newer** (python.org) and **VS Code** with the *Python* extension.
2. In VS Code: **File → Open Folder…** and choose this `urdu-chatbot` folder.
3. Open the terminal inside VS Code: **Terminal → New Terminal**.
4. Create a *virtual environment* (a private box of packages just for this project):

   ```
   Windows:        py -m venv .venv
   Mac / Linux:    python3 -m venv .venv
   ```
5. Turn it on (you will see `(.venv)` at the start of the terminal line):

   ```
   Windows:        .venv\Scripts\activate
   Mac / Linux:    source .venv/bin/activate
   ```
   If VS Code asks "use this environment for the workspace?", click **Yes**.
   (Windows PowerShell error about scripts? Run `Set-ExecutionPolicy -Scope Process RemoteSigned` and try again.)
6. Install the packages:

   ```
   pip install -r requirements.txt
   ```
   This is big (~1 GB) because `sentence-transformers` brings the AI library PyTorch. Only the document-search part needs it.
7. Add your Groq key. Copy `.env.example` to a new file named `.env` and replace the text after `=`:

   ```
   GROQ_API_KEY=gsk_your_real_key_here
   ```
   `.env` is listed in `.gitignore`, so it will never be uploaded to GitHub. **Never paste your key into a `.py` file or share it.**
8. Check that your model names exist: `python list_models.py`. If a name in `chatbot/config.py` is missing from that list, replace it.

## 2. Run things

| What | Command (or press ▶ in VS Code: **Run and Debug** panel, pick a name) |
|---|---|
| Chat with the bot | `python main.py` |
| Chat + search the documents | `python main.py --rag` |
| Same, better for Roman Urdu questions | `python main.py --rag --translate-queries` |
| Test the language detector (free, instant) | `python -m evaluation.eval_language_detection` |
| Compare the two models | `python -m evaluation.compare_models` (try `--limit 10` first) |
| Test cross-language document search | `python -m evaluation.eval_retrieval` |
| Run the unit tests | `python -m unittest discover -s tests -t . -v` |

Chat examples to try: `kya hal hai`, `kia haal hai`, `delivery mein kitna time lagta hai?`, `ڈیلیوری میں کتنے دن لگتے ہیں؟`, then `please reply in English`.

> Urdu in the VS Code terminal: the letters can look separated or flipped because terminals do not support right-to-left text well. That is only display; the text is correct. `results/model_comparison.csv` (open in Excel) shows Urdu properly.

---

## 3. How it works, in plain words

Every time you send a message, the bot does four steps:

```
your message
    │
    ▼
1. DETECT the language          (language_detect.py)   "roman_urdu"
    │
    ▼
2. RETRIEVE helpful paragraphs  (retrieval.py)         "Delivery: 2 to 3 working days..."
    │
    ▼
3. BUILD the instructions       (chatbot.py)           "Reply ONLY in Roman Urdu... use ONLY these documents..."
    │
    ▼
4. ASK the AI model on Groq     (llm.py)               → reply
```

### Files, one by one

**`chatbot/config.py`**: all settings in one place: folder paths, model names, how many paragraphs to fetch. It reads your key from `.env`. If you want to try another model, change it here.

**`chatbot/language_detect.py`**: decides which language to reply in. No AI is used, only rules:
- Urdu script lives in its own Unicode range, so any word in those letters is Urdu.
- For English letters, the code has two word lists: English words and Roman Urdu words *with many spellings* (`kya / kia / kiya`, `hal / haal`, `hai / hy`). Each word is looked up. Unknown words get a "fuzzy" match to catch typos (`delivry`, `kesay`). Stretched words (`kyaaaa`) are squeezed first.
- The counts decide the reply: if at least 40% of recognised words are Urdu or Roman Urdu, reply in that language, otherwise English. So `Please check my order status bhai` gets English, while `Mera order track kar do please` gets Roman Urdu.
- `LanguageTracker` keeps replies **consistent** during a chat: it remembers the language, keeps it when you send just `ok` or an emoji, and obeys `please reply in English` / `roman urdu mein jawab do` until you change it.

**`chatbot/llm.py`**: the only file that talks to Groq. Sends messages, returns text, and waits and retries when Groq says "too many requests" (common on free plans).

**`chatbot/retrieval.py`**: searches the English documents with an Urdu question. It uses *embeddings*: a multilingual model turns every sentence into a list of numbers that captures meaning, so an Urdu question and the English paragraph about the same thing get similar numbers. Search = find the closest numbers (*cosine similarity*). Optional trick: translate a Roman Urdu question to English first (`--translate-queries`) because the embedding model knows little Roman Urdu.

**`chatbot/chatbot.py`**: glues steps 1–4 together. The *system prompt* is a hidden instruction message. It is rebuilt every turn with the current reply language and the retrieved paragraphs, and it tells the AI to use only those documents and never invent facts.

**`main.py`**: the terminal chat loop (`input()`, call the bot, `print()`).

**`data/docs/*.txt`**: the shop's English knowledge (returns, delivery, payments...). First line = title; paragraphs separated by blank lines. Add your own `.txt` files and they are searched automatically.

**`data/eval_set.json`**: 70 test messages (English, Urdu, Roman Urdu, mixed), including spelling variations. Each has the *correct* reply language and its meaning in English.

**`data/retrieval_eval.json`**: 19 test questions with the document that should be found.

**`evaluation/`**: three scripts that measure quality (next section).

**`tests/`**: small automatic checks. Green = nothing broke.

---

## 4. Evaluation: what each script measures

**Language detection** (`eval_language_detection`): accuracy of the detector against the human answers, per message type, plus a list of mistakes and a spelling-variation consistency check.

**Model comparison** (`compare_models`): the same messages go to two Groq models (`llama-3.3-70b-versatile` vs `llama-3.1-8b-instant`, set in `config.py`). For each reply:
- **language_ok**: did the reply come out in the requested language (checked by our detector)?
- **understanding** and **language_quality** (1–5): given by a third "judge" model (`openai/gpt-oss-120b`), different from the two being compared so it does not grade itself.
- **seconds**: speed.

Use `--no-judge` for only the free language check. Results are saved to `results/model_comparison.csv`; **read some replies yourself**, since an AI judge is useful but imperfect.

**Retrieval** (`eval_retrieval`): `hit@1` = the right document is the top result; `hit@3` = it is among the top 3 chunks. It compares *direct search* with *translate-then-search*, split by Urdu / Roman Urdu / English questions.

### Your results (fill in after running)

| Check | Model / strategy | Result |
|---|---|---|
| Language detection accuracy | rules | 95.7% on the included set (67/70) |
| Reply language OK | llama-3.3-70b-versatile | _fill in_ |
| Reply language OK | llama-3.1-8b-instant | _fill in_ |
| Understanding (1–5) | 70b vs 8b | _fill in_ |
| Retrieval hit@1 / hit@3 | direct | _fill in_ |
| Retrieval hit@1 / hit@3 | translate-then-search | _fill in_ |

---

## 5. Known limits (honest list)

- The detector only knows words in its lists. `data/eval_set.json` was used while improving them, so 95.7% is **optimistic**. Collect new messages from friends (real WhatsApp style) for a fair test.
- Three included examples are genuinely hard and the detector misses them: `cash on delivery available hai?` and `order cancel kar do please` (mostly English words, but a Roman Urdu person would want a Roman Urdu reply), and `Can you cancel my order? Abhi abhi kiya tha` (ambiguous). A trained classifier (e.g. fastText) would be the next level.
- "Roman Urdu" has no official spelling. More spellings in `ROMAN_URDU_WORDS` = better detection.
- The AI judge and the language check are automatic and imperfect.
- The shop, prices and phone numbers in `data/docs` are made up.

## 6. Ideas to extend (good practice)

1. Add 20 new messages to `eval_set.json` and see the score change.
2. Add words to `ROMAN_URDU_WORDS` and re-run the detection evaluation.
3. Add a third model to `MODELS_TO_COMPARE`.
4. Write your own documents in `data/docs/` and ask questions in Urdu.
5. Build a small web page for the chatbot (Urdu shows better in a browser than in a terminal).
