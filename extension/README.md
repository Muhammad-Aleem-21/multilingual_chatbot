# Website Chat extension (Chrome / Edge)

For hosting without running Python on your computer, follow [DEPLOY_FREE.md](../DEPLOY_FREE.md). Settings now accept a hosted HTTPS server address and a persistent access token.

1. In the project terminal run `pip install -r requirements.txt` if needed. Keep your Groq key in the existing project `.env` file.
2. Run `python extension_server.py`. Keep the terminal open. The first question loads/downloads the multilingual embedding model and can take several minutes.
3. Open `chrome://extensions` (or `edge://extensions`), enable **Developer mode**, choose **Load unpacked**, and select this `extension` folder.
4. Click the extension toolbar icon to open settings. Paste the **Extension server token** printed in the terminal and save. The token changes whenever you restart the server.
5. Refresh a normal website tab. Click **Ask this site** at the bottom right. Ask in English, Urdu script or Roman Urdu.

## Reading a website

- Each question refreshes the current page's collected text. **Read this page** collects it without making an AI call.
- **Read linked pages** follows same-origin HTML links, up to 20 attempted new pages per click. Repeat for more pages. It includes authentication cookies for same-origin requests, skips redirects and common action URLs, and never submits forms. Crawling performs GET requests; only use it on sites where reading links is appropriate.
- Navigate to other pages in the **same tab** and collect them to include dynamically rendered content or dashboard pagination. The collection and recent chat remain available for that tab and origin until you clear them, close the tab, or restart the browser. They are stored in browser session memory, not synced.
- Answers show clickable source URLs. The widget reports collection counts, skipped pages and truncation. Each page is limited to its first 50,000 characters; the collection is limited to 100 pages / 1.2 million characters. It does not promise exhaustive website coverage.
- The current page is always supplied directly to the answer model so titles and visible counts do not depend on search similarity. Logo alt text and link destinations are collected too. Link destinations are not verified HTTP redirect chains.
- Replies answer the specific question in simple language: usually one sentence for a fact or 1–3 sentences for an explanation. Ask for details or all items when you want a longer answer. Sources appear separately below the reply.
- **Clear** removes the current tab/origin's collection and conversation. Server embedding caches hold up to four collections in memory; stop the server to erase them.

## Access and privacy

No page text is sent to the backend until you ask a question. Questions send the current collection to your local server; the server sends the question, recent chat, relevant excerpts, and optional translated search queries to Groq. Do not collect content you are not permitted to share with Groq. Form controls and scripts are excluded, but displayed personal information can be collected.

The extension displays its widget on HTTP(S) sites. The background worker contacts the configured server: the local loopback API by default or an HTTPS server whose domain you approve in settings. The server requires an access token. The Groq key is never stored in the extension.

Browser internal pages, extension stores, PDFs, cross-origin frames, shadow-root content, canvas content and inaccessible pages are not supported. Fetched HTML does not execute JavaScript, so linked app dashboards may yield only a shell. Open those pages and use **Read this page** after the records render. Hidden users, virtualized rows, backend-only records and entire-database counts need a separate authorized API integration. This version does not connect to private dashboard APIs or databases.

## Troubleshooting

- No widget: refresh the tab after installing/reloading the extension and check its site-access permissions.
- Connection error: start the local server and verify the token in settings. The extension uses port 8765.
- Poor answer: check collected pages and sources; collect the page containing the missing information. Search is approximate and model answers can be wrong.
- After editing extension files, click **Reload** on the extensions page and refresh website tabs.

Run offline checks from the project root: `python -B -m unittest discover -s tests -t . -v`.
