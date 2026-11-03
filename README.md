# Roman Urdu & Multilingual Chatbot: What It Does

**Browser extension:** See [extension/README.md](extension/README.md) to install the floating website chat widget in Chrome or Edge. Start its backend with `python extension_server.py`.

**Free hosted extension API:** Follow [DEPLOY_FREE.md](DEPLOY_FREE.md) for PythonAnywhere Beginner hosting without payment details. Use `requirements-hosted.txt` for the small hosted backend.

A chatbot that understands **English, Urdu (اردو), Roman Urdu** (Urdu typed in English letters, e.g. `kya hal hai`) and **mixed messages**, replies in the right language, and can answer **from documents** even when the question and the document are in different languages.

---

## 1. Language detection and reply language

For every message the bot decides which language to reply in. It uses plain rules, with no AI model:

- **Urdu script:** recognised by its letters.
- **Roman Urdu vs English:** each word is looked up in two word lists. The Roman Urdu list holds many spellings (`kya / kia / kiya`, `hal / haal`, `hai / hy`). Typos such as `delivry` and stretched words such as `kyaaaa` are also handled.
- **Reply rule:** if at least 40% of the recognised words are Urdu or Roman Urdu, the bot replies in that language (Urdu script if there is more of it, otherwise Roman Urdu). Otherwise it replies in English.

| Message | Detected | Reply in |
|---|---|---|
| `Where is my order?` | English | English |
| `آپ کیسے ہیں؟` | Urdu | Urdu |
| `kia haal hai` | Roman Urdu | Roman Urdu |
| `Mera order track kar do please` | Mixed | Roman Urdu |
| `Please check my order status bhai` | Mixed | English |

**Staying consistent during a chat:**
- Asking for a language ("please reply in English", "roman urdu mein jawab do") switches to it and keeps it until you ask again.
- An unreadable message (emoji, digits) keeps the previous language.
- A tiny English message such as "ok" or "thanks" inside an Urdu chat does not switch the language.

---

## 2. Answering from documents (search)

Every message follows the same path:

```
message → language → (search documents) → build instructions → AI model → reply
```

The sidebar setting **Answer from documents** gives four cases:

| Setting | What the bot uses |
|---|---|
| Off | General AI knowledge only. It will not invent shop facts and suggests contacting support. |
| On, Built-in shop documents | The `.txt` files in `data/docs/` (fictional shop DesiMart) |
| On, Upload my own files | Only the files you upload (`.txt`, `.md`, `.pdf`) |
| On, Upload chosen but no file yet | A warning is shown and the bot answers without documents |

**How the search works:**
1. **Translate:** an Urdu or Roman Urdu question is also translated to English by Groq. English questions are not translated. If one model fails, the next is tried.
2. **Score:** a multilingual model scores every document paragraph by *meaning*. The better score of the original and translated question is kept.
3. **Select:** the 3 best paragraphs above the minimum score (0.25) are the hits.
4. **Expand:** if a hit comes from a short document, the whole document is passed on. For a long document, only the hit and its neighbouring paragraphs are passed.
5. **Answer:** the AI is told to answer only from this text, in the reply language, and never to invent facts.

**If nothing relevant is found,** the bot says it could not find the answer in the documents and suggests rephrasing or contacting support.

**Your own files:** each file is cut into pieces of at most about 500 characters. The search index is built once per upload and lives only in your session. Scanned PDFs (pictures of text) cannot be read.

---

## 3. Two modes on the web page

**Chat mode:** a normal conversation with one model. The last 6 turns are remembered. Under each reply you see the detected language, the reply language, the documents used and, if used, the English version of your question that was searched.

**Compare two models mode:** one question goes to Model A and Model B. Both get the same instructions and the same documents, and the question stands alone, with no chat history. A third model, the judge, then scores both replies. The page shows:
- how the judge read the question, and the better answer with a reason
- scores out of 10 for understanding, language quality, helpfulness, and use of the documents (when documents are on), plus an overall average
- what each model thought you asked, with one strength and one weakness
- measured facts: speed, length, and whether the reply was in the requested language
- a side-by-side summary table

The judge sees the two replies in random order, so it cannot favour the first. An AI judge is helpful but not perfect, so read the answers yourself too.

---

## 4. Evaluation (separate from the web page)

| What | Command |
|---|---|
| Language detection accuracy on 70 messages (spelling variations included) | `python -m evaluation.eval_language_detection` |
| Compare two models on the same messages (language check + AI judge scores) | `python -m evaluation.compare_models` |
| Does an Urdu / Roman Urdu question find the right English document? | `python -m evaluation.eval_retrieval` |
| See the real search scores for one question | `python -m evaluation.check_retrieval "your question"` |
| Run the automatic tests | `python -m unittest discover -s tests -t . -v` |

Test data lives in `data/eval_set.json` (70 messages) and `data/retrieval_eval.json` (19 questions).

---

## 5. Limits

- The language detector only knows the words in its lists. Add words to improve it.
- Search uses only your latest message, so a follow-up like "and in Lahore?" may not find the right paragraph.
- Search quality for Roman Urdu depends on the English translation step working.
- The 70 evaluation messages were written by hand, and the word lists were tuned on them, so the 95.7% detection score is optimistic.
- The shop, prices and phone numbers in `data/docs/` are made up.
