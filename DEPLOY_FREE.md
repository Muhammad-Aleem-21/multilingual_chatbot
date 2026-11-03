# Free hosting without payment details: PythonAnywhere

Use the **Beginner (free)** account at https://www.pythonanywhere.com/registration/register/beginner/ . Its signup asks for username, email and password, not card details. This is limited free hosting, not an unlimited production service. You must renew the web app using the expiry/extend button in the Web tab each month.

The hosted backend uses small Flask dependencies, text search and optional Groq query translation. It does not install PyTorch, NumPy or an embedding model. Your current Streamlit app and local embedding search continue separately. Cross-page search is approximate and less semantic than the local embedding search. Relevant passages can be selected even beyond the first 18,000 characters of the current page; the answer model receives the current-page prefix plus the top ten matching passages.

## 1. Create the free account

Create and verify your PythonAnywhere Beginner account. Open **Consoles → Bash**. You do not need a Railway, Render or Hugging Face account for this method.

## 2. Upload the prepared backend ZIP

In PythonAnywhere **Files**, upload the local file `dist/website-chat-backend.zip` into your home directory. In its Bash console run:

```bash
mkdir -p ~/website-chat
unzip -o ~/website-chat-backend.zip -d ~/website-chat
cd ~/website-chat
python3.11 -m venv ~/.virtualenvs/website-chat
source ~/.virtualenvs/website-chat/bin/activate
pip install --no-cache-dir -r requirements-hosted.txt
```

Use a Python version available in the console and choose exactly the same version when creating the web app. Do not install the root `requirements.txt`; it includes packages too large for the free disk quota.

## 3. Save the API key privately and generate an extension token

While still in `~/website-chat` with the virtualenv active, run:

```bash
python -c 'import getpass,secrets,pathlib; key=getpass.getpass("Groq API key (hidden): "); token=secrets.token_urlsafe(32); p=pathlib.Path(".env"); p.write_text("GROQ_API_KEY="+key.strip()+"\nWEBSITE_API_TOKENS="+token+"\n"); p.chmod(0o600); print("Extension access token:",token)'
```

Paste your existing Groq API key at the hidden prompt. Save the printed **extension access token** somewhere private; use it in the extension later. The command creates the server's `.env` without printing the Groq key. Run it only for initial setup: rerunning it replaces the token. Never share your Groq API key with extension users.

## 4. Create the web app

1. Open **Web → Add a new web app**. Accept the free `YOURUSERNAME.pythonanywhere.com` domain.
2. Choose **Manual configuration** and **Python 3.11** (or the same version used above).
3. In **Virtualenv**, enter `/home/YOURUSERNAME/.virtualenvs/website-chat`.
4. Open the **WSGI configuration file** link. Replace its contents with the contents of the uploaded `website-chat/pythonanywhere_wsgi.py` file, then save. The provided file uses your home directory automatically, so no username edits are needed in it.
5. Set **Source code** and **Working directory**, if present, to `/home/YOURUSERNAME/website-chat`.
6. Click the green **Reload** button.
7. Open `https://YOURUSERNAME.pythonanywhere.com/health`. Expected response: `{"status":"ok"}`.

Do not start `python extension_server.py` or `flask run` in the hosting console. PythonAnywhere runs the app via its Web tab.

## 5. Connect your browser extension

1. Open `chrome://extensions` or `edge://extensions` and reload the extension. For a new installation, load the `extension` folder unpacked (or extract `dist/website-chat-extension.zip` first).
2. Open the extension's settings using its toolbar icon.
3. Set **Server address** to `https://YOURUSERNAME.pythonanywhere.com`, without `/chat` or `/health`.
4. Set **Access token** to the token printed in step 3. Click **Save settings** and approve the API-domain permission prompt.
5. Refresh a normal website tab and ask a question. You can stop the local server; this uses the hosted API.

## Limits and privacy

- Free PythonAnywhere accounts have 512 MiB of disk, one web worker and a web-app expiry of one month. Review the Web tab expiry and renew it before it expires. This is for light use and testing, not many concurrent users.
- Outbound networking is restricted, but `api.groq.com` is on PythonAnywhere's free allowlist. The extension collects pages in the browser; the backend does not crawl arbitrary websites.
- Groq is a separate service. Stay within your account's free allowance; API rate limits can prevent answers. Hosting does not provide unlimited free AI calls.
- Default limits are 20 requests per access token per hour and 200 total per hour. The small `usage.sqlite3` file stores token hashes and request timestamps only; no website content, chat or raw access token is written to it.
- For another invited user, generate another random token, append it to `.env`'s `WEBSITE_API_TOKENS` value separated by a comma, and reload the web app. Removing a token revokes its access after reload. No public registration is provided.
- Questions send collected website content to your hosted API, then relevant excerpts and recent chat to Groq. Only share content you are permitted to process this way.
- `/health` tests the server only. Ask a real extension question to verify the Groq key and provider connectivity. For a 502, check the Web tab's error log; logs intentionally omit question text and provider credentials.

Official sources checked November 2, 2026:

- Signup: https://www.pythonanywhere.com/registration/register/beginner/
- Free limits: https://help.pythonanywhere.com/pages/FreeAccountsFeatures/
- Groq allowlist: https://www.pythonanywhere.com/whitelist/
- Flask/WSGI setup: https://help.pythonanywhere.com/pages/Flask/
