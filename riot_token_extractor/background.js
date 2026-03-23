const API_BASE = "http://localhost:5000";

async function sendJSON(path, data) {
  try {
    const r = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  } catch (e) {
    console.error("POST", path, e);
  }
}

// --- helpers cookies ---
async function getAllCookiesFor(url, fpd) {
  try {
    // Firefox supporte firstPartyDomain: on tente 2 variantes
    const a = await browser.cookies.getAll(fpd ? { url, firstPartyDomain: fpd } : { url });
    return a;
  } catch {
    // fallback sans fpd
    return await browser.cookies.getAll({ url });
  }
}

async function dumpRiotCookies() {
  const urls = ["https://auth.riotgames.com/", "https://riotgames.com/"];
  const fpds = [undefined, "auth.riotgames.com", "riotgames.com"];

  const out = {};
  for (const url of urls) {
    for (const fpd of fpds) {
      const arr = await getAllCookiesFor(url, fpd);
      for (const c of arr) {
        if (c.domain.endsWith("riotgames.com")) {
          out[c.name] = c.value;
        }
      }
    }
  }
  console.log("🍪 Riot cookies:", out);
  await sendJSON("/cookies", { domain: "riotgames.com", cookies: out });
}

/* 1) Access token via URL fragment */
browser.webRequest.onBeforeRequest.addListener(
  details => {
    try {
      if (details.url.includes("#access_token=")) {
        const m = details.url.match(/access_token=([^&]+)/);
        if (m) {
          const token = m[1];
          console.log("✅ Access Token:", token);
          sendJSON("/token", { token });
          dumpRiotCookies();
        }
      }
    } catch (e) {
      console.error("onBeforeRequest error", e);
    }
    return {};
  },
  { urls: ["<all_urls>"] },
  ["blocking"]
);

/* 2) Dump à chaque navigation Riot */
browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!changeInfo.url && changeInfo.status !== "complete") return;
  const url = changeInfo.url || tab.url || "";
  try {
    const h = new URL(url).hostname;
    if (h && h.endsWith("riotgames.com")) dumpRiotCookies();
  } catch {}
});

/* 3) Au démarrage */
browser.runtime.onInstalled.addListener(dumpRiotCookies);
browser.runtime.onStartup.addListener(dumpRiotCookies);

/* 4) Sur changement de cookie Riot */
browser.cookies.onChanged.addListener(info => {
  try {
    const c = info.cookie;
    if (c && c.domain && c.domain.endsWith("riotgames.com")) dumpRiotCookies();
  } catch {}
});
