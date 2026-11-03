const input = document.querySelector("#token");
const endpoint = document.querySelector("#endpoint");
chrome.storage.local.get(["token", "endpoint"]).then(data => {
  input.value = data.token || "";
  endpoint.value = data.endpoint || "http://127.0.0.1:8765";
});
document.querySelector("#save").addEventListener("click", async () => {
  try {
    const url = new URL(endpoint.value.trim());
    if (url.username || url.password || url.search || url.hash || url.pathname !== "/") throw new Error("Enter just the server address, without /chat, /health or credentials.");
    if (url.protocol !== "https:" && url.origin !== "http://127.0.0.1:8765") throw new Error("Hosted servers must use HTTPS.");
    if (!input.value.trim()) throw new Error("Enter an access token.");
    if (url.protocol === "https:") {
      const granted = await chrome.permissions.request({origins: [`${url.origin}/*`]});
      if (!granted) throw new Error("Server permission declined; settings were not saved.");
    }
    await chrome.storage.local.set({token: input.value.trim(), endpoint: url.origin});
    document.querySelector("#status").textContent = "Saved. Refresh a website and click Ask this site.";
  } catch (error) { document.querySelector("#status").textContent = error.message; }
});
