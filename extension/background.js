chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
chrome.tabs.onRemoved.addListener(async id => {
  const entries = await chrome.storage.session.get(null);
  const keys = Object.keys(entries).filter(key => key.startsWith(`site:${id}:`));
  if (keys.length) await chrome.storage.session.remove(keys);
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (["load", "save", "clear"].includes(message.type) && sender.tab) {
    const key = `site:${sender.tab.id}:${new URL(sender.url).origin}`;
    (async () => {
      try {
        if (message.type === "clear") await chrome.storage.session.remove(key);
        if (message.type === "save") {
          if (JSON.stringify(message.state).length > 3000000) throw new Error("Collection is full. Clear pages to start again.");
          await chrome.storage.session.set({[key]: message.state});
        }
        respond({ok: true, state: (await chrome.storage.session.get(key))[key]});
      } catch (error) { respond({ok: false, error: error.message}); }
    })();
    return true;
  }
  if (message.type === "settings") {
    chrome.runtime.openOptionsPage();
    respond({ok: true});
    return;
  }
  if (message.type !== "chat" || !sender.tab) return;
  (async () => {
    try {
      const {token = "", endpoint = "http://127.0.0.1:8765"} = await chrome.storage.local.get(["token", "endpoint"]);
      if (!token) throw new Error("Enter your server address and access token in Settings.");
      const api = new URL(endpoint);
      if (api.origin !== endpoint || (api.protocol !== "https:" && api.origin !== "http://127.0.0.1:8765")) throw new Error("Invalid server address. Check Settings.");
      const origin = new URL(sender.url).origin;
      if (!Array.isArray(message.pages) || message.pages.some(p => new URL(p.url).origin !== origin)) {
        throw new Error("Only pages from this website can be used.");
      }
      const response = await fetch(`${api.origin}/chat`, {
        method: "POST",
        redirect: "error",
        headers: {"Content-Type": "application/json", Authorization: `Bearer ${token}`},
        body: JSON.stringify({question: message.question, pages: message.pages, history: message.history, current_url: message.current_url}),
        signal: AbortSignal.timeout(240000)
      });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || "Server error");
      respond({ok: true, ...data});
    } catch (error) {
      respond({ok: false, error: `${error.message} Check your server address and access token in Settings.`});
    }
  })();
  return true;
});
