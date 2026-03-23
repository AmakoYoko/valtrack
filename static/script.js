const btn = document.getElementById("btn");
const out = document.getElementById("out");
const overlay = document.getElementById("overlay");
const frame = document.getElementById("authFrame");
function setCookie(name, value, days=1) {
  const expires = new Date(Date.now()+days*864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; Expires=${expires}; Path=/; SameSite=Lax`;
}
function getCookie(name) {
  return document.cookie.split('; ').reduce((acc, v) => {
    const [k, val] = v.split('=');
    return k === name ? decodeURIComponent(val) : acc;
  }, null);
}
async function startLogin() {
  // 1) demande une session
  const r = await fetch("/request_login", { method: "POST" });
  if (!r.ok) { out.textContent = "Erreur /request_login"; return; }
  const data = await r.json();
  await new Promise(res => setTimeout(res, 3000));
  // 2) ouvre l’iframe plein écran
  frame.src = data.browser_url;       // page de login (conteneur)
  overlay.classList.remove("hidden");

  // 3) poll /wait_token jusqu’à réception
  const sid = data.session_id;
  const start = Date.now();
  const TIMEOUT_MS = 2 * 60 * 1000;   // 2 min (adapter si besoin)

  while (Date.now() - start < TIMEOUT_MS) {
    await new Promise(res => setTimeout(res, 1500));
    const w = await fetch(`/wait_token?session_id=${encodeURIComponent(sid)}&timeout=1`);
    if (!w.ok) continue;
    const ans = await w.json();
    console.log(ans)
    if (ans.access_token) {
      // 4) token OK → ferme l’iframe et affiche
      overlay.classList.add("hidden");
      frame.src = "about:blank";
      out.textContent = `Access Token Riot:\n${ans.access_token}`;
      setCookie("riot_token", ans.access_token, 1); // 1 jour

      return;
    }
  }

  out.textContent = "Timeout sans token.";
  overlay.classList.add("hidden");
  frame.src = "about:blank";
}

btn.addEventListener("click", startLogin);


const walletBtn = document.getElementById("walletBtn");
const walletOut = document.getElementById("walletOut");

walletBtn.onclick = async () => {
  const token = getCookie("riot_token");
  if (!token) { walletOut.textContent = "Pas de token en cookie."; return; }

  const r = await fetch("/valorant/wallet", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  if (!r.ok) { walletOut.textContent = "Erreur wallet"; return; }
  const data = await r.json();
  walletOut.textContent = JSON.stringify(data, null, 2);
};


const storeBtn = document.getElementById("storeBtn");
const storeOut = document.getElementById("storeOut");

storeBtn.onclick = async () => {
  const token = getCookie("riot_token");
  if (!token) { storeOut.textContent = "Pas de token en cookie."; return; }

  const r = await fetch("/valorant/featured_store", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  if (!r.ok) { walletOut.textContent = "Erreur featured_store"; return; }
  const data = await r.json();
  storeOut.textContent = JSON.stringify(data, null, 2);
};



const UserInfoBtn = document.getElementById("UserInfoBtn");
const UserInfoOut = document.getElementById("UserInfoOut");

UserInfoBtn.onclick = async () => {
  const token = getCookie("riot_token");
  if (!token) { UserInfoOut.textContent = "Pas de token en cookie."; return; }

  const r = await fetch("/valorant/get_user_info", {
    headers: { "Authorization": `Bearer ${token}` }
  });
  if (!r.ok) { walletOut.textContent = "Erreur get_user_info"; return; }
  const data = await r.json();
  UserInfoOut.textContent = JSON.stringify(data, null, 2);
};


