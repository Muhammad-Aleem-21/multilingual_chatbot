(() => {
  if (document.getElementById("website-chat-extension")) return;
  const host = document.createElement("div");
  host.id = "website-chat-extension";
  document.documentElement.append(host);
  const root = host.attachShadow({mode: "closed"});
  root.innerHTML = `
    <style>
    :host{all:initial;position:fixed;bottom:22px;right:22px;z-index:2147483647;font:14px system-ui;color:#16352f}
    *{box-sizing:border-box}button,input{font:inherit}button{cursor:pointer;border:0;border-radius:9px;padding:9px 12px;background:#e8f1ee;color:#173e35}button:disabled{opacity:.5;cursor:wait}
    #launcher{background:#12695d;color:white;padding:15px 21px;box-shadow:0 6px 28px #0003;border-radius:28px;font-weight:650}
    #panel{width:390px;max-width:calc(100vw - 30px);height:600px;max-height:calc(100vh - 100px);background:#fff;border:1px solid #dbe6e2;border-radius:18px;box-shadow:0 12px 55px #0003;display:flex;flex-direction:column;overflow:hidden;margin-bottom:12px}
    #panel[hidden]{display:none}header{padding:16px;background:#12695d;color:white;display:flex;align-items:center;gap:10px}header strong{flex:1}header button{background:#ffffff22;color:white}
    .tools{padding:12px;border-bottom:1px solid #e4ece8;display:flex;gap:6px;flex-wrap:wrap}#status{font-size:12px;width:100%;line-height:1.5;color:#526a62}#messages{flex:1;overflow:auto;padding:14px;background:#f7faf8}.message{padding:11px 13px;margin:0 0 12px;border-radius:12px;background:#fff;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.55;border:1px solid #e5ece8}.user{background:#e0f0e8;margin-left:25px}.source{display:block;font-size:12px;margin-top:7px;color:#12695d}form{display:flex;gap:7px;padding:12px}input{min-width:0;flex:1;border:1px solid #cadbd3;border-radius:9px;padding:11px}form button{background:#12695d;color:white}.note{font-size:11px;padding:0 13px 12px;color:#65796e}
    </style>
    <section id="panel" hidden aria-label="Website chat"><header><strong>Ask this website</strong><button id="settings" title="Settings">Settings</button><button id="close" aria-label="Close chat">×</button></header>
    <div class="tools"><button id="collect">Read this page</button><button id="crawl">Read linked pages</button><button id="clear">Clear</button><div id="status" role="status">No pages collected.</div></div>
    <div id="messages" role="log" aria-live="polite"></div><form><input aria-label="Your question" placeholder="Ask in English, اردو, Roman Urdu" maxlength="4000" required><button id="send">Send</button></form>
    <div class="note">Questions send collected text to your configured server and relevant excerpts to Groq. Linked-page reading covers up to 20 HTML pages per run.</div></section>
    <button id="launcher" aria-expanded="false">✦ Ask this site</button>`;
  const $ = selector => root.querySelector(selector);
  let pages = [], history = [], busy = false, crawling = false;
  const rpc = message => chrome.runtime.sendMessage(message);
  const status = text => { $("#status").textContent = text || `${pages.length} page(s) collected. Refresh a page after its content changes.`; };
  const save = async () => {
    const result = await rpc({type: "save", state: {pages, history}});
    if (!result.ok) throw new Error(result.error);
  };
  function bubble(text, role = "assistant", sources = []) {
    const div = document.createElement("div");
    div.className = `message ${role}`;
    div.dir = "auto";
    div.textContent = text;
    for (const url of sources) {
      try {
        if (new URL(url).origin !== location.origin) continue;
        const a = document.createElement("a");
        a.className = "source"; a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = url;
        div.append(a);
      } catch { /* Ignore invalid source URLs. */ }
    }
    $("#messages").append(div);
    $("#messages").scrollTop = $("#messages").scrollHeight;
  }
  function canonical(raw, base = location.href) {
    try {
      const url = new URL(raw, base); url.hash = "";
      if (url.origin !== location.origin || !/^https?:$/.test(url.protocol)) return null;
      if (/\b(logout|logoff|signout|delete|remove|unsubscribe|checkout|purchase)\b/i.test(url.pathname + url.search)) return null;
      return url.href;
    } catch { return null; }
  }
  function extract(doc, url, live) {
    const copy = doc.body?.cloneNode(true);
    if (!copy) throw new Error("No readable page body found.");
    if (live) {
      const originals = [...doc.body.querySelectorAll("*")];
      const copies = [...copy.querySelectorAll("*")];
      originals.forEach((el, i) => {
        const style = getComputedStyle(el);
        if (style.display === "none" || style.visibility === "hidden") copies[i].remove();
      });
    }
    copy.querySelectorAll("script,style,noscript,iframe,svg,input,textarea,select,button,[hidden],[aria-hidden='true'],#website-chat-extension").forEach(el => el.remove());
    // University/site names are often logo alt text rather than text nodes.
    copy.querySelectorAll("img[alt]").forEach(el => el.replaceWith(` ${el.getAttribute("alt")} `));
    copy.querySelectorAll("[aria-label]").forEach(el => {
      if (!el.textContent.trim()) el.append(` ${el.getAttribute("aria-label")} `);
    });
    // Preserve boundaries between rows and block elements in extracted text.
    copy.querySelectorAll("p,div,li,tr,h1,h2,h3,section,article,br").forEach(el => el.append("\n"));
    copy.querySelectorAll("td,th").forEach(el => el.append(" | "));
    const text = (copy.textContent || "").replace(/[\t ]+/g, " ").replace(/\n\s*\n/g, "\n\n").trim();
    if (!text) throw new Error("This page has no readable text.");
    const truncated = text.length > 50000;
    const anchors = [...copy.querySelectorAll("a[href]")];
    const linkRows = [...new Set(anchors.map(a => {
      try {
        const target = new URL(a.getAttribute("href"), url);
        if (!/^https?:$/.test(target.protocol)) return null;
        return `${a.textContent.trim() || a.getAttribute("title") || target.hostname}: ${target.href}`;
      } catch { return null; }
    }).filter(Boolean))];
    const links = anchors.map(a => canonical(a.getAttribute("href"), url)).filter(Boolean);
    const combined = `PAGE TITLE: ${doc.title}\nPAGE URL: ${url}\n\nVISIBLE PAGE CONTENT:\n${text}\n\nPAGE LINKS (destinations, not verified HTTP redirects):\n${linkRows.join("\n")}`;
    return {page: {url, text: combined.slice(0, 50000)}, links, truncated: truncated || combined.length > 50000};
  }
  function add(page) {
    const index = pages.findIndex(p => p.url === page.url);
    if (index >= 0) pages[index] = page;
    else if (pages.length < 100 && pages.reduce((n, p) => n + p.text.length, 0) + page.text.length <= 1200000) pages.push(page);
    else throw new Error("Collection limit reached (100 pages or 1.2 million characters). Clear to start again.");
  }
  async function collect() {
    const url = canonical(location.href);
    if (!url) throw new Error("This page URL is not supported for collection.");
    const result = extract(document, url, true);
    add(result.page); await save();
    status(`${pages.length} page(s) collected.${result.truncated ? " Current page limited to its first 50,000 characters." : " Current page refreshed."}`);
    return result.links;
  }
  $("#launcher").onclick = () => {
    $("#panel").hidden = !$("#panel").hidden;
    $("#launcher").setAttribute("aria-expanded", String(!$("#panel").hidden));
    if (!$("#panel").hidden) $("input").focus();
  };
  $("#close").onclick = () => { $("#panel").hidden = true; $("#launcher").setAttribute("aria-expanded", "false"); };
  $("#settings").onclick = () => rpc({type: "settings"});
  $("#collect").onclick = async () => { if (busy || crawling) return; try { await collect(); } catch (e) { status(e.message); } };
  $("#clear").onclick = async () => {
    if (busy || crawling) return;
    pages = []; history = [];
    $("#messages").replaceChildren(); await rpc({type: "clear"}); status();
  };
  $("#crawl").onclick = async () => {
    if (busy || crawling) return;
    crawling = true; $("#crawl").disabled = true;
    let read = 0, skipped = 0, truncated = 0;
    try {
      const queue = await collect(), seen = new Set(pages.map(p => p.url));
      while (queue.length && read + skipped < 20) {
        const url = queue.shift();
        if (seen.has(url)) continue;
        seen.add(url); status(`Reading linked pages… ${read} read, ${skipped} skipped.`);
        try {
          const response = await fetch(url, {credentials: "same-origin", redirect: "error", signal: AbortSignal.timeout(12000)});
          if (!response.ok || !response.headers.get("content-type")?.includes("text/html")) throw new Error("Not HTML");
          // Stream with a byte limit so large downloads cannot consume unlimited memory.
          const reader = response.body.getReader(), decoder = new TextDecoder();
          let html = "", size = 0;
          try {
            while (true) {
              const part = await reader.read(); if (part.done) break;
              size += part.value.length;
              if (size > 2000000) throw new Error("Page too large");
              html += decoder.decode(part.value, {stream: true});
            }
            html += decoder.decode();
          } finally { await reader.cancel(); }
          const result = extract(new DOMParser().parseFromString(html, "text/html"), url, false);
          add(result.page); read++; if (result.truncated) truncated++;
          for (const link of result.links) if (!seen.has(link) && queue.length < 2000) queue.push(link);
        } catch { skipped++; }
      }
      await save(); status(`${pages.length} pages collected. ${read} linked pages added; ${skipped} skipped; ${truncated} truncated. Dynamic pages may need to be opened manually.`);
    } catch (e) { status(e.message); }
    finally { crawling = false; $("#crawl").disabled = false; }
  };
  $("form").onsubmit = async event => {
    event.preventDefault(); if (busy || crawling) return;
    const question = $("input").value.trim(); if (!question) return;
    busy = true; $("#send").disabled = true;
    try {
      await collect();
      bubble(question, "user"); $("input").value = ""; status("Searching collected pages and preparing an answer…");
      const result = await rpc({type: "chat", question, pages, history, current_url: canonical(location.href)});
      if (!result.ok) throw new Error(result.error);
      bubble(result.text, "assistant", result.sources);
      history.push({role: "user", content: question}, {role: "assistant", content: result.text});
      history = history.slice(-12); await save();
      status(result.translation_error ? "Answered, but English query translation failed; search used the original text." : undefined);
    } catch (e) { bubble(e.message); status("Question could not be completed. Check settings and the local server."); }
    finally { busy = false; $("#send").disabled = false; }
  };
  rpc({type: "load"}).then(result => {
    if (result.state) {
      pages = result.state.pages || []; history = result.state.history || [];
      history.forEach(item => bubble(item.content, item.role));
    } else bubble("Ask about this page in English, Urdu or Roman Urdu. Use Read linked pages to include more of this website. Only collected content can be searched.");
    status();
  }).catch(e => status(e.message));
})();
