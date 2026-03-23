# app.py
import os, uuid, socket, time, subprocess, requests, threading
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Header
import base64
from bs4 import BeautifulSoup
import sqlite3
from pathlib import Path
from router_henrik import router as henrik_router
from ports_manager import pick_login_ports, release_login_ports
import asyncio
from pywebpush import webpush, WebPushException
import datetime as dt
from urllib.parse import urlparse

CLIENT_PLATFORM_JSON = (
    '{"platformType":"PC","platformOS":"Windows","platformOSVersion":"10.0.19045.1.256.64bit","platformChipset":"Unknown"}'
)
VAPID_PUBLIC  = "BMZlxNqE7QOBbab15Xkg-nCDoxou_8naaatSyF3quAlgMaRjMJDLSlJ36SPIxWv3eIKAXnvTl7HNmiEI0oqMmqM"
VAPID_PRIVATE = "YcpFoCxfryQgHkrTqkfTGBi1l9uj5zHQizggiRL6h38"
VAPID_CLAIMS  = {"sub": "mailto:laura.pinto@lamas.one"}
VAPID_SUB     = os.getenv("VAPID_SUB", "mailto:laura.pinto@lamas.one")

# --- Config ---
HOST = os.getenv("PUBLIC_HOST", "lamas.one")
IMAGE_NAME = os.getenv("IMAGE_NAME", "riot-auth")
# SESSION_TTL = int(os.getenv("SESSION_TTL", "120"))  # 10 min
SESSION_TTL = int(os.getenv("SESSION_TTL", "10"))  # 10 min

POLL_INTERVAL = 2  # secondes

app = FastAPI()
app.include_router(henrik_router)
SUBS = set()  # stocke les JSON stringify des subscriptions

app.mount("/static", StaticFiles(directory="static"), name="static")

# ==== [Monolithic Auth + DB + Riot Link] =====================================
# Simple user accounts + sessions in SQLite, and Riot token/cookies attachment.
import base64, hashlib, secrets, sqlite3, datetime, json
from typing import Optional, Tuple
from fastapi import Depends
import os, re, socket


APP_DB = os.environ.get("APP_DB", "app.db")

def _db():
    con = sqlite3.connect(APP_DB)
    con.row_factory = sqlite3.Row
    return con

def _now_utc() -> str:
    return datetime.datetime.utcnow().isoformat()

def _plus_days(days: int) -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat()

def _hash_pw(password: str, salt: bytes=None):
    if salt is None:
        salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return base64.b64encode(salt).decode(), base64.b64encode(h).decode()

def _verify_pw(password: str, salt_b64: str, hash_b64: str) -> bool:
    salt = base64.b64decode(salt_b64); expected = base64.b64decode(hash_b64)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return secrets.compare_digest(h, expected)

def _init_db():
    con = _db(); cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        pw_salt TEXT NOT NULL,
        pw_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS riot_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        access_token TEXT,
        cookies_json TEXT,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS webpush_subscriptions (
  id INTEGER PRIMARY KEY,
  endpoint TEXT UNIQUE NOT NULL,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  user_agent TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_seen  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_webpush_last_seen ON webpush_subscriptions(last_seen);

    """); con.commit(); con.close()

@app.on_event("startup")
def _auth_startup():
    _init_db()

# ---- Models (inline, simple parsing) ----
from pydantic import BaseModel, EmailStr, constr

class RegisterIn(BaseModel):
    email: EmailStr
    password: constr(min_length=8)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class SessionOut(BaseModel):
    session_token: str
    expires_at: str

def _extract_session_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization: return None
    parts = authorization.split(" ", 1)
    if len(parts)==2 and parts[0].lower() in ("session","bearer"):
        return parts[1]
    return None

def require_user(authorization: Optional[str] = Header(default=None, alias="Authorization")) -> int:
    token = _extract_session_token(authorization)
    if not token: raise HTTPException(status_code=401, detail="Missing session")
    con = _db(); cur = con.cursor()
    cur.execute("SELECT user_id, expires_at FROM sessions WHERE token=?", (token,))
    row = cur.fetchone(); con.close()
    if not row: raise HTTPException(status_code=401, detail="Invalid session")
    if datetime.datetime.fromisoformat(row["expires_at"]) < datetime.datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired")
    return row["user_id"]

def resolve_riot_token_from_user(user_id: int) -> str:
    con = _db(); cur = con.cursor()
    cur.execute("SELECT access_token FROM riot_accounts WHERE user_id=?", (user_id,))
    row = cur.fetchone(); con.close()
    if not row or not row["access_token"]:
        raise HTTPException(status_code=400, detail="No Riot account linked")
    return row["access_token"]

def save_riot_bundle(user_id: int, access_token: str, cookies_json: str):
    con = _db(); cur = con.cursor()
    cur.execute("SELECT id FROM riot_accounts WHERE user_id=?", (user_id,))
    if cur.fetchone():
        cur.execute("UPDATE riot_accounts SET access_token=?, cookies_json=?, updated_at=? WHERE user_id=?",
                    (access_token, cookies_json, _now_utc(), user_id))
    else:
        cur.execute("INSERT INTO riot_accounts(user_id, access_token, cookies_json, updated_at) VALUES(?,?,?,?)",
                    (user_id, access_token, cookies_json, _now_utc()))
    con.commit(); con.close()

# ---- Auth endpoints ----
@app.post("/auth/register")
def _register(body: RegisterIn):
    con = _db(); cur = con.cursor()
    salt_b64, hash_b64 = _hash_pw(body.password)
    try:
        cur.execute("INSERT INTO users(email, pw_salt, pw_hash, created_at) VALUES(?,?,?,?)",
                    (body.email.lower(), salt_b64, hash_b64, _now_utc()))
        con.commit()
    except sqlite3.IntegrityError:
        con.close(); raise HTTPException(status_code=409, detail="Email already registered")
    con.close(); return {"ok": True}

@app.post("/auth/login", response_model=SessionOut)
def _login(body: LoginIn):
    con = _db(); cur = con.cursor()
    cur.execute("SELECT id, pw_salt, pw_hash FROM users WHERE email=?", (body.email.lower(),))
    row = cur.fetchone()
    if not row or not _verify_pw(body.password, row["pw_salt"], row["pw_hash"]):
        con.close(); raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_urlsafe(48); exp = _plus_days(30)
    cur.execute("INSERT INTO sessions(token, user_id, expires_at, created_at) VALUES(?,?,?,?)",
                (token, row["id"], exp, _now_utc()))
    con.commit(); con.close()
    return {"session_token": token, "expires_at": exp}

@app.post("/auth/logout")
def _logout(authorization: Optional[str] = Header(default=None, alias="Authorization")):
    token = _extract_session_token(authorization)
    if not token: raise HTTPException(status_code=401, detail="Missing session")
    con = _db(); cur = con.cursor()
    cur.execute("DELETE FROM sessions WHERE token=?", (token,))
    con.commit(); con.close()
    return {"ok": True}

# ---- Riot account link endpoints ----
@app.get("/riot/link/start")
def _riot_link_start():
    # Client-side: open /login to perform Riot auth with your existing flow
    return {"next": "/login", "message": "Open /login, complete Riot auth, then call /riot/link/complete"}
from typing import Dict, Optional
from pydantic import BaseModel
from fastapi import HTTPException, Depends
class LinkIn(BaseModel):
    access_token: str
    cookies: Optional[Dict[str, str]] = None  # optionnel
from fastapi import Request, HTTPException, Depends

@app.post("/riot/link/complete")
async def riot_link_complete(request: Request, user_id: int = Depends(require_user)):
    try:
        data = await request.json()  # doit être du JSON
    except Exception:
        raise HTTPException(400, "Body must be JSON")

    token = (data.get("access_token") or data.get("token") or "").strip()
    cookies = data.get("cookies") or {}
    if not token:
        raise HTTPException(400, "Missing access_token")

    save_riot_bundle(user_id, token, json.dumps(cookies))
    return {"ok": True}
# ==============================================================================
ClientPlatform = base64.b64encode(CLIENT_PLATFORM_JSON.encode()).decode()

def _find_cookies_sqlite(container: str) -> str:
    # cherche le fichier cookies.sqlite du profil Firefox
    cmd = ["docker","exec",container,"sh","-lc","find /root/.mozilla/firefox -name cookies.sqlite | head -n1"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    return p.stdout.strip()

def _copy_cookies_sqlite(container: str, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    src = _find_cookies_sqlite(container)
    if not src:
        return None
    subprocess.run(["docker","cp",f"{container}:{src}",str(dest_path)], check=True)
    return dest_path

def _extract_riot_cookies(sqlite_path: Path) -> dict:
    out = {}
    if not sqlite_path or not sqlite_path.exists():
        return out
    conn = sqlite3.connect(str(sqlite_path))
    try:
        cur = conn.cursor()
        # moz_cookies schema (Firefox)
        cur.execute("""
            SELECT host, name, value FROM moz_cookies
            WHERE host LIKE '%riotgames.com%'
        """)
        for host,name,val in cur.fetchall():
            out.setdefault(host,{})[name]=val
    finally:
        conn.close()
    return out
def get_valorant_version():
    r = requests.get("https://valorant-api.com/v1/version", timeout=10)
    r.raise_for_status()
    return r.json()["data"]["riotClientVersion"]

def get_player_id(token: str):
    r = requests.get(
        "https://auth.riotgames.com/userinfo",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    r.raise_for_status()
    return r.json()["sub"]

def get_entitlements(token: str):
    r = requests.post(
        "https://entitlements.auth.riotgames.com/api/token/v1",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=10
    )
    r.raise_for_status()
    return r.json()["entitlements_token"]

def get_user_info(token: str, puuids: list[str], region="eu"):

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),    }
    url = f"https://pd.eu.a.pvp.net/name-service/v2/players"
    r = requests.request("PUT", url, json=puuids, headers=headers)
    r.raise_for_status()
    return r.json()







def get_wallet(token: str):
    puuid = get_player_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),
    }
    r = requests.get(f"https://pd.eu.a.pvp.net/store/v1/wallet/{puuid}", headers=headers, timeout=10)
    r.raise_for_status()
    j = r.json()
    return {
        "valorant_point": j["Balances"]["85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"],
        "kindom_point": j["Balances"]["85ca954a-41f2-ce94-9b45-8ca3dd39a00d"],
        "radianite_point": j["Balances"]["e59aa87c-4cbf-517a-5983-6e81511be9b7"],
    }


def get_tier_info(tier: int):
    r = requests.get("https://valorant-api.com/v1/competitivetiers?language=fr-FR", timeout=10)
    r.raise_for_status()
    j = r.json()
    tiers = (j.get("data") or [{}])[0].get("tiers", [])
    return next((t for t in tiers if t.get("tier") == tier), None)


def get_current_rank(token: str):
    puuid = get_player_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),
    }
    r = requests.get(f"https://pd.eu.a.pvp.net/mmr/v1/players/{puuid}", headers=headers, timeout=10)

    r.raise_for_status()
    j = r.json()
    return {
        "tier": j["LatestCompetitiveUpdate"]["TierAfterUpdate"],
        "rr": j["LatestCompetitiveUpdate"]["RankedRatingAfterUpdate"],
        "info": get_tier_info(j["LatestCompetitiveUpdate"]["TierAfterUpdate"])

    }



def get_competitive_updates(token: str, limit: int = 50, queue: str = "competitive", shard: str = "eu"):
    """
    Paginate l'endpoint PD:
    GET https://pd.{shard}.a.pvp.net/mmr/v1/players/{puuid}/competitiveupdates
        ?queue=competitive&startIndex=X&endIndex=Y   (Y <= 20)
    Retourne un objet proche du format Riot.
    """
    puuid = get_player_id(token)

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,           # déjà présent chez toi
        "X-Riot-ClientVersion": get_valorant_version(),    # idem
        "X-Riot-Entitlements-JWT": get_entitlements(token) # idem
    }

    base = f"https://pd.{shard}.a.pvp.net"
    path = f"/mmr/v1/players/{puuid}/competitiveupdates"

    all_matches = []
    start_index = 0

    while len(all_matches) < limit:
        remaining = limit - len(all_matches)
        page_size = min(20, remaining)  # hard limit côté PD

        params = {
            "queue": queue,
            "startIndex": start_index,
            "endIndex": page_size,      # ici sert de "count" (<=20)
        }

        r = requests.get(base + path, headers=headers, params=params, timeout=10)
        if r.status_code == 404:
            # plus d'historique dispo
            break
        r.raise_for_status()

        j = r.json()
        matches = j.get("Matches", []) or []
        all_matches.extend(matches)

        # si on récupère moins que demandé, on a atteint la fin
        if len(matches) < page_size:
            break

        start_index += len(matches)

    return {
        "Version": 0,
        "Subject": puuid,
        "Matches": all_matches,
        "count": len(all_matches),
        "queue": queue,
        "shard": shard,
    }

def get_storefront(token: str):
    puuid = get_player_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),
    }
    r = requests.post(
        f"https://pd.eu.a.pvp.net/store/v3/storefront/{puuid}",
        headers=headers,
        json={},  # <-- JSON vide dans le body
        timeout=10
    )
    r.raise_for_status()
    return r.json()




def get_loadout(token: str):
    puuid = get_player_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),
    }
    r = requests.get(
        f"https://pd.eu.a.pvp.net/personalization/v3/players/{puuid}/playerloadout",
        headers=headers,
        timeout=10
    )
    r.raise_for_status()
    return r.json()


def get_ownedItems(token: str):
    puuid = get_player_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),
    }
    r = requests.get(
        f"https://pd.eu.a.pvp.net/store/v1/entitlements/{puuid}",
        headers=headers,
        timeout=10
    )
    r.raise_for_status()
    return r.json()





def get_matchhistory(token: str):
    puuid = get_player_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),
    }
    r = requests.get(
        f"https://pd.eu.a.pvp.net/match-history/v1/history/{puuid}",
        headers=headers,
        timeout=10
    )
    r.raise_for_status()
    return r.json()

def get_lastmatch(token: str):
    puuid = get_player_id(token)
    matchid = get_matchhistory(token)["History"][0]["MatchID"]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Riot-ClientPlatform": ClientPlatform,
        "X-Riot-ClientVersion": get_valorant_version(),
        "X-Riot-Entitlements-JWT": get_entitlements(token),
    }
    r = requests.get(
        f"https://pd.eu.a.pvp.net/match-details/v1/matches/{matchid}",
        headers=headers,
        timeout=10
    )
    r.raise_for_status()
    return r.json()



def get_valo_video(rel_url: str) -> str:
    if not rel_url:
        return ""
    try:
        r = requests.get("https://valorantinfo.kr/" + rel_url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        src = (soup.find("source") or {}).get("src", "")
        return src or ""
    except Exception:
        return ""
API_WEAPONS = "https://valorant-api.com/v1/weapons?language=fr-FR"


def fetch_weapons(timeout=12):
    r = requests.get(API_WEAPONS, timeout=timeout)
    r.raise_for_status()
    return r.json().get("data", [])

def build_uuid_index(weapons):
    """
    Retourne:
      - idx: dict uuid -> {"match_type": ..., "weapon_uuid": ..., "skin_uuid": ...}
      - by_weapon: dict weapon_uuid -> weapon_full_object
    """
    idx = {}
    by_weapon = {}
    for w in weapons:
        w_uuid = w.get("uuid")
        by_weapon[w_uuid] = w
        idx[w_uuid] = {"match_type": "weapon", "weapon_uuid": w_uuid}

        for s in w.get("skins") or []:
            s_uuid = s.get("uuid")
            if s_uuid:
                idx[s_uuid] = {"match_type": "skin", "weapon_uuid": w_uuid, "skin_uuid": s_uuid}

            for lvl in s.get("levels") or []:
                l_uuid = lvl.get("uuid")
                if l_uuid:
                    idx[l_uuid] = {"match_type": "level", "weapon_uuid": w_uuid, "skin_uuid": s_uuid}

            for ch in s.get("chromas") or []:
                c_uuid = ch.get("uuid")
                if c_uuid:
                    idx[c_uuid] = {"match_type": "chroma", "weapon_uuid": w_uuid, "skin_uuid": s_uuid}
    return idx, by_weapon

def get_weapon_full_by_any_uuid(target_uuid: str, weapons_cache=None):
    """
    Donne n'importe quel UUID (weapon/skin/level/chroma) →
    -> {"weapon": <objet complet>, "match": {...}} ou None si pas trouvé.
    """
    weapons = weapons_cache or fetch_weapons()
    idx, by_weapon = build_uuid_index(weapons)
    hit = idx.get(target_uuid)
    if not hit:
        return None
    return {"weapon": by_weapon[hit["weapon_uuid"]], "match": hit}


def get_skin_information(uuid: str):
    # url = f"https://valorantinfo.kr/skin_details/{uuid}"
    # try:
    #     r = requests.get(url, timeout=10)
    #     r.raise_for_status()
    # except Exception:
    #     return {"name": "", "know_cost": "", "variation": {}}

    # soup = BeautifulSoup(r.text, "html.parser")
    # skin_info = soup.find("div", class_="skin-info")

    # h2 = (skin_info.find("h2").get_text(strip=True) if skin_info and skin_info.find("h2") else "")
    # p1 = (skin_info.find("p").get_text(strip=True).replace("Price: ","").replace("vp","")
    #       if skin_info and skin_info.find("p") else "")

    # out = {}
    # for a in soup.find_all("a", class_="skin-link") or []:
    #     name = (a.find("p").get_text(strip=True) if a and a.find("p") else "")
    #     href = a.get("href") if a else ""
    #     img = (a.find("img").get("src") if a and a.find("img") else "")
    #     out[name] = {"video": get_valo_video(href), "img": img}
    print(get_weapon_full_by_any_uuid(uuid)["match"])
    weapon = get_weapon_full_by_any_uuid(uuid)["match"]["skin_uuid"]
    url = f"https://valorant-api.com/v1/weapons/skins/{weapon}?language=fr-FR"
    r = requests.get(url)
    return r.json()


def get_front_featured_store(token: str):

    sf = get_storefront(token)
    out = {}
    for x in sf.get("SkinsPanelLayout", {}).get("SingleItemStoreOffers", []):
        out[x["OfferID"]] = {
            "name": get_skin_information(x["OfferID"]),
            "cost": x["Cost"]["85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741"]
        }
    return out





@app.get("/")
def root():
    return FileResponse("static/index.html")
@app.get("/app")
def root():
    return FileResponse("static/app.html")
@app.get("/login")
def root():
    return FileResponse("static/login.html")
@app.get("/weapon")
def root():
    return FileResponse("static/weapon.html")
@app.get("/list_weapon")
def root():
    return FileResponse("static/list_weapon.html")
@app.get("/agents")
def root():
    return FileResponse("static/agents.html")

@app.get("/bundles")
def root():
    return FileResponse("static/bundles.html")

@app.get("/bundle")
def root():
    return FileResponse("static/bundle.html")

@app.get("/shareshop")
def root():
    return FileResponse("static/shareshop.html")

@app.get("/loadout")
def root():
    return FileResponse("static/loadout.html")
@app.get("/rank")
def root():
    return FileResponse("static/rank.html")

@app.get("/matches")
def root():
    return FileResponse("static/matches.html")
@app.get("/matchinfo")
def root():
    return FileResponse("static/matchinfo.html")
@app.get("/sw.js")
def root():
    return FileResponse("static/sw.js", media_type="application/javascript", headers={"Cache-Control":"no-cache"})

@app.get("/app/sw.js")
def root():
    return FileResponse("static/sw.js", media_type="application/javascript", headers={"Cache-Control":"no-cache"})
@app.get("/app/manifest.webmanifest")
def root():
    FileResponse("static/manifest.webmanifest", media_type="application/manifest+json")
@app.get("/app/index.html")
def root():
    return FileResponse("static/app.html")

from fastapi.responses import PlainTextResponse
@app.get("//riot.txt", response_class=PlainTextResponse)
def root():
    return "d2b9a226-252f-4088-ad35-184acde2dfd2"






# sid -> {name, web_port, api_port, created, expires}
sessions = {}
lock = threading.Lock()
def _find_session_by_container(name: str):
    with lock:
        for sid, s in sessions.items():
            if s.get("name") == name:
                return sid, s.get("web_port"), s.get("api_port")
    return None, None, None




async def stop_container(name: str, web_port: int | None = None, api_port: int | None = None, session_id: str | None = None):
    # Résoudre ports si manquants
    if web_port is None or api_port is None:
        sid, wp, ap = _find_session_by_container(name)
        session_id = session_id or sid
        web_port = web_port or wp
        api_port = api_port or ap

    # Stop docker (idempotent)
    try:
        subprocess.run(["docker", "stop", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        # Release ports si connus
        if web_port is not None and api_port is not None:
            await release_login_ports(web_port, api_port)

        # Nettoyer la session liée
        if session_id:
            with lock:
                sessions.pop(session_id, None)
def build_image():
    subprocess.run(["docker", "build", "-t", IMAGE_NAME, "."], check=True)

def start_container(name: str, web_port: int, api_port: int):
    return subprocess.Popen([
        "docker", "run", "--rm",
        "--name", name,
        "-p", f"{web_port}:10000",
        "-p", f"{api_port}:5000",
        IMAGE_NAME
    ])

# --- Janitor ---
def _janitor():
    print("janitor")
    while True:
        now = time.time()
        to_kill = []
        with lock:
            for sid, info in list(sessions.items()):
                expires = info["expires"]
                remaining = expires - now
                print(
                    f"[{sid}] {info['name']} - now={now:.2f}, expires={expires:.2f}, reste={remaining:.2f}s"
                )
                if now > expires:
                    print("APPEND KILL", info["name"])
                    to_kill.append((sid, info["name"]))
        for sid, cname in to_kill:
            print("TO KILL", cname)
            asyncio.run(stop_container(cname))

            with lock:
                sessions.pop(sid, None)
        time.sleep(5)

@app.on_event("startup")
def start_janitor():
    threading.Thread(target=_janitor, daemon=True).start()

# --- API ---

@app.post("/request_login")
async def request_login(force_build: bool = Query(False, description="Rebuild l'image avant de lancer")):
    # 0) build si besoin
    if force_build:
        build_image()
    else:
        build_image()
        # si image absente, build (fallback rapide)
        missing = subprocess.run(
            ["docker", "image", "inspect", IMAGE_NAME],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode != 0
        if missing:
            build_image()

    # 1) ports dispo ?
    choice = await pick_login_ports()
    if not choice.get("ok"):
    # if choice.get("ok"):
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "message": "Tous les serveurs de login sont occupés. Merci de patienter.",
                "retry_after": choice.get("retry_after", 15)
            }
        )

    web_port = choice["web_port"]
    api_port = choice["api_port"]

    # 2) démarrer le conteneur
    sid = uuid.uuid4().hex[:8]
    name = f"riot-auth-{sid}"
    try:
        # ton start_container DOIT mapper les ports dynamiques passés ici
        # équivalent docker run:
        #   -p {web_port}:10000  -p {api_port}:10001
        start_container(name, web_port, api_port)
    except Exception as e:
        # libérer la réservation en cas d'échec
        await release_login_ports(web_port, api_port)
        return JSONResponse(status_code=500, content={"ok": False, "error": f"Start failed: {e}"})

    # 3) enregistrer la session
    now = time.time()
    with lock:
        sessions[sid] = {
            "name": name,
            "web_port": web_port,
            "api_port": api_port,
            "created": now,
            "expires": now + SESSION_TTL,
        }

    # 4) réponse OK
    return {
        "ok": True,
        "session_id": sid,
        "browser_url": f"http://{HOST}:{web_port}/",
        "token_poll_url": f"/wait_token?session_id={sid}",
        "web_port": web_port,
        "api_port": api_port,
    }

@app.get("/wait_token")
def wait_token(session_id: str, timeout: int = 120):
    with lock:
        info = sessions.get(session_id)
    if not info:
        raise HTTPException(404, "Session inconnue ou expirée")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if time.time() > info["expires"]:

            asyncio.run(stop_container(info["name"]))

            with lock: sessions.pop(session_id, None)
            raise HTTPException(410, "Session expirée")

        try:
            r = requests.get(f"http://127.0.0.1:{info['api_port']}/bundle", timeout=2)
            b = r.json()
            token = b.get("token")
            print(token)
            cookies = b.get("cookies")
            if token:
                # # 1) copie cookies.sqlite du conteneur vers l’hôte
                # dest = Path(f"tmp/{info['name']}_cookies.sqlite")
                # try:
                #     copied = _copy_cookies_sqlite(info["name"], dest)
                # except Exception:
                #     copied = None

                # # 2) lit les cookies Riot depuis le fichier copié (si présent)
                # cookies = _extract_riot_cookies(copied) if copied else {}

                # 3) stoppe le conteneur et renvoie
                asyncio.run(stop_container(info["name"]))
                with lock: sessions.pop(session_id, None)
                return {
                    "access_token": token,
                    "cookies": cookies
                }
        except Exception:
            pass

        time.sleep(POLL_INTERVAL)

    with lock:
        if session_id in sessions:
            sessions[session_id]["expires"] = time.time() + SESSION_TTL
    return {"access_token": None, "ready": False}



@app.post("/cancel")
def cancel(session_id: str):
    with lock:
        info = sessions.pop(session_id, None)
    if not info:
        raise HTTPException(404, "Session inconnue")
    asyncio.run(stop_container(info["name"]))
    return {"ok": True}

@app.get("/valorant/version")
def api_version():
    return {"riotClientVersion": get_valorant_version()}

@app.get("/valorant/wallet")
def api_wallet(user_id: int = Depends(require_user)):
    # Authorization: Bearer <token>
    
    riot_token = resolve_riot_token_from_user(user_id)
    print(riot_token)
    return get_wallet(riot_token)

@app.get("/valorant/storefront")
def api_storefront(user_id: int = Depends(require_user)):
    riot_token = resolve_riot_token_from_user(user_id)
    return get_storefront(riot_token)

@app.get("/valorant/skin/{uuid}")
def api_skin(uuid: str):
    return get_skin_information(uuid)

@app.get("/valorant/featured_store")
def api_featured_store(user_id: int = Depends(require_user)):
    riot_token = resolve_riot_token_from_user(user_id)
    return get_front_featured_store(riot_token)

@app.get("/valorant/get_user_profile/{puuid}")
def api_getglobaluserinfo(puuid: str, user_id: int = Depends(require_user)):
    # Authorization: Bearer <token>
    riot_token = resolve_riot_token_from_user(user_id)
    print(puuid)
    return get_user_info(riot_token, [puuid])

@app.get("/valorant/get_user_info")
def api_userinfo(user_id: int = Depends(require_user)):
    # Authorization: Bearer <token>
    riot_token = resolve_riot_token_from_user(user_id)
    puuid = get_player_id(riot_token)
    print(puuid)
    return get_user_info(riot_token, [puuid])[0]

@app.get("/valorant/get_matchhistory")
def api_get_matchhistory(user_id: int = Depends(require_user)):
    riot_token = resolve_riot_token_from_user(user_id)
    return get_matchhistory(riot_token)

@app.get("/valorant/get_lastmatch")
def api_get_lastmatch(user_id: int = Depends(require_user)):
    riot_token = resolve_riot_token_from_user(user_id)
    return get_lastmatch(riot_token)

@app.get("/valorant/get_skin_information")
def api_get_lastmatch(uuid: str = ""):
    return get_skin_information(uuid)

@app.get("/valorant/get_current_rank")
def api_get_current_rank(user_id: int = Depends(require_user)):
    riot_token = resolve_riot_token_from_user(user_id)
    return get_current_rank(riot_token)

@app.get("/valorant/get_loadout")
def api_get_loadout(user_id: int = Depends(require_user)):
    riot_token = resolve_riot_token_from_user(user_id)
    return get_loadout(riot_token)


@app.get("/valorant/get_ownedItems")
def api_get_ownedItems(user_id: int = Depends(require_user)):
    riot_token = resolve_riot_token_from_user(user_id)
    return get_ownedItems(riot_token)





# Route: /valorant/competitive_updates
@app.get("/valorant/competitive_updates")
def api_competitive_updates(
    limit: int = 50,                    # 50 / 100 / 200 max
    queue: str = "competitive",
    user_id: int = Depends(require_user),
):
    """
    Aggrège les pages PD (max 20 par appel) jusqu'à 'limit'.
    """
    limit = max(1, min(limit, 200))     # borne raisonnable
    riot_token = resolve_riot_token_from_user(user_id)
    return get_competitive_updates(riot_token, limit=limit, queue=queue)




# === Refresh via /authorize?prompt=none (cookies RSO) ===
import json, base64, datetime, urllib.parse as up, requests, sqlite3

AUTH_URL = (
    "https://auth.riotgames.com/authorize"
    "?client_id=play-valorant-web-prod"
    "&redirect_uri=https%3A%2F%2Fplayvalorant.com%2Fopt_in"
    "&response_type=token%20id_token&scope=openid&nonce=1&prompt=none"
)

def _db():
    con = sqlite3.connect(APP_DB)
    con.row_factory = sqlite3.Row
    return con

def _b64pad(s): return s + "=" * (-len(s) % 4)
def _jwt_exp(tok: str):
    try:
        p = tok.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(_b64pad(p)).decode()).get("exp")
        return datetime.datetime.utcfromtimestamp(int(exp)) if exp else None
    except: return None

def _cookies_from_json(cj: str):
    try:
        d = json.loads(cj or "{}")
        if isinstance(d, dict): return d
        if isinstance(d, list): return {c["name"]: c["value"] for c in d if "name" in c and "value" in c}
    except: pass
    return {}

def _riot_cookie_reauth(cookies_dict: dict) -> dict:
    # attend cookies sous clé "riotgames.com" (comme ton script)
    ck = cookies_dict.get("riotgames.com", {})
    if not ck.get("ssid"):
        raise RuntimeError("cookie 'ssid' manquant")

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    })
    # Pose cookies sur le bon domaine
    s.cookies.set("ssid", ck["ssid"], domain="auth.riotgames.com")
    for k in ("sub", "clid", "csid"):
        if ck.get(k): s.cookies.set(k, ck[k], domain="auth.riotgames.com")

    url = AUTH_URL
    if ck.get("__Secure-id_token") or ck.get("id_token"):
        url += "&id_token_hint=" + up.quote(ck.get("__Secure-id_token") or ck["id_token"])

    r = s.get(url, allow_redirects=False, timeout=10)
    if r.status_code not in (302, 303):
        raise RuntimeError(f"reauth failed: HTTP {r.status_code}")
    frag = up.urlparse(r.headers.get("Location","")).fragment
    q = dict(up.parse_qsl(frag))
    if "access_token" not in q:
        raise RuntimeError("reauth error: pas d'access_token")
    return {"access_token": q["access_token"], "id_token": q.get("id_token",""), "expires_in": int(q.get("expires_in","3600"))}

def refresh_user_from_db_cookies(user_id: int) -> dict:
    con = _db(); cur = con.cursor()
    cur.execute("SELECT cookies_json FROM riot_accounts WHERE user_id=?", (user_id,))
    row = cur.fetchone(); con.close()
    if not row: return {"user_id": user_id, "found": False}

    cookies = _cookies_from_json(row["cookies_json"])
    try:
        res = _riot_cookie_reauth(cookies)
    except Exception as e:
        # marque relink si KO
        con = _db(); cur = con.cursor()
        cur.execute("UPDATE riot_accounts SET needs_relink=1, updated_at=datetime('now') WHERE user_id=?", (user_id,))
        con.commit(); con.close()
        return {"user_id": user_id, "ok": False, "error": str(e), "needs_relink": True}

    exp = _jwt_exp(res["access_token"])
    con = _db(); cur = con.cursor()
    cur.execute("""UPDATE riot_accounts
                   SET access_token=?, expires_at=?, updated_at=datetime('now'), needs_relink=0
                   WHERE user_id=?""",
                (res["access_token"], (exp.isoformat() if exp else None), user_id))
    con.commit(); con.close()
    return {"user_id": user_id, "ok": True, "expires_at": (exp.isoformat() if exp else None)}

# Endpoints
@app.post("/admin/riot/refresh_me_cookie")
def api_refresh_me_cookie(user_id: int = Depends(require_user)):
    return refresh_user_from_db_cookies(user_id)

@app.post("/admin/riot/refresh_all_cookie")
def api_refresh_all_cookie(user_id: int = Depends(require_user)):
    con = _db(); cur = con.cursor()
    cur.execute("SELECT user_id FROM riot_accounts"); uids = [r["user_id"] for r in cur.fetchall()]
    con.close()
    out = []
    for uid in uids:
        out.append(refresh_user_from_db_cookies(int(uid)))
    return {"total": len(out), "items": out}


# ==== Auto-refresh 10 min avant expiration (cookies) ====
import os, time, threading, datetime

AUTO_COOKIE_REFRESH = os.getenv("VAL_RIOT_AUTO_COOKIE_REFRESH", "1") == "1"
SCAN_PERIOD_SEC     = int(os.getenv("VAL_RIOT_SCAN_PERIOD", "60"))      # scan / 60s
REFRESH_WINDOW_SEC  = int(os.getenv("VAL_RIOT_REFRESH_WINDOW", "600"))  # 10 min

def _list_accounts():
    con=_db(); cur=con.cursor()
    cur.execute("SELECT user_id, access_token FROM riot_accounts WHERE access_token IS NOT NULL AND access_token!=''")
    rows=cur.fetchall(); con.close()
    return rows

def _should_refresh(token: str) -> bool:
    exp = _jwt_exp(token)
    if not exp:  # token illisible -> tente refresh
        return True
    return (exp - datetime.datetime.utcnow()) <= datetime.timedelta(seconds=REFRESH_WINDOW_SEC)

def _auto_cookie_refresh_loop():
    while True:
        try:
            for r in _list_accounts():
                uid = int(r["user_id"]); tok = r["access_token"] or ""
                if _should_refresh(tok):
                    try: refresh_user_from_db_cookies(uid)
                    except: pass
                time.sleep(0.05)
        except Exception:
            pass
        time.sleep(SCAN_PERIOD_SEC)

@app.on_event("startup")
def _start_auto_cookie_refresh():
    if AUTO_COOKIE_REFRESH:
        threading.Thread(target=_auto_cookie_refresh_loop, daemon=True).start()

# Endpoint manuel: ne refresh que ceux “à échéance”
@app.post("/admin/riot/refresh_due_cookie")
def api_refresh_due_cookie(user_id: int = Depends(require_user)):
    out = {"refreshed":0, "skipped":0, "items":[]}
    for r in _list_accounts():
        uid=int(r["user_id"]); tok=r["access_token"] or ""
        if _should_refresh(tok):
            res = refresh_user_from_db_cookies(uid)
            out["items"].append(res); out["refreshed"] += int(res.get("ok",0))
        else:
            out["items"].append({"user_id":uid,"skipped":True}); out["skipped"] += 1
    return out

# --- Helpers Riot ---
import math, time, requests
from fastapi import Query, HTTPException, Depends


def get_puuid(token: str) -> str:
    r = requests.get(
        "https://auth.riotgames.com/userinfo",
        headers={"Authorization": f"Bearer {token}"}, timeout=8)
    if not r.ok:
        raise HTTPException(502, "userinfo failed")
    return r.json()["sub"]

def pd(shard="eu"):  # adapte si besoin
    return f"https://pd.{shard}.a.pvp.net"

def _pd_get(url, token, ent, params=None, tries=3):
    for i in range(tries):
        r = requests.get(
            url, params=params, timeout=10,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Riot-ClientPlatform": ClientPlatform,
                "X-Riot-ClientVersion": get_valorant_version(),
                "X-Riot-Entitlements-JWT": get_entitlements(token),
            }
        )
        if r.status_code == 429:
            time.sleep(1.0 + i*0.5); continue
        if r.ok: return r.json()
        if 500 <= r.status_code < 600:
            time.sleep(0.5); continue
        break
    raise HTTPException(r.status_code, r.text[:200])

# --- Endpoint: récupère tout l'historique (avec limite) ---
@app.get("/valorant/match_history")
def match_history(
    limit: int = Query(default=0, ge=0),             # 0 = tout
    page_size: int = Query(default=20, ge=1, le=50), # fenêtre (endIndex-startIndex)
    shard: str = Query(default="eu"),
    user_id: int = Depends(require_user),
):
    token = resolve_riot_token_from_user(user_id)
    ent   = get_entitlements(token)
    puuid = get_puuid(token)
    
    # 1ère page pour connaître Total
    start, end = 0, page_size
    first = _pd_get(f"{pd(shard)}/match-history/v1/history/{puuid}",
                    token, ent, params={"startIndex": start, "endIndex": end})
    total = int(first.get("Total", 0))
    wanted = total if limit in (0, None) else min(limit, total)

    history = first.get("History", []) or []
    fetched = len(history)

    # calcule le nombre de pages restantes
    while fetched < wanted:
        start = fetched
        end   = min(fetched + page_size, wanted)
        j = _pd_get(f"{pd(shard)}/match-history/v1/history/{puuid}",
                    token, ent, params={"startIndex": start, "endIndex": end})
        history.extend(j.get("History", []) or [])
        fetched = len(history)

    # coupe si on a demandé moins que Total
    if wanted and fetched > wanted:
        history = history[:wanted]

    return {
        "Subject": puuid,
        "Total": total,
        "Fetched": len(history),
        "History": history,
    }


from typing import Optional, List
from fastapi import Query

def _resolve_path(obj, path: str):
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list) and seg.isdigit() and int(seg) < len(cur):
            cur = cur[int(seg)]
        else:
            return None
    return cur

@app.get("/valorant/match/{match_id}")
def valorant_match_details(
    match_id: str,
    shard: str = "eu",
    filter: Optional[str] = Query(default=None, description="Ex: matchInfo,players"),
    user_id: int = Depends(require_user),
):
    token = resolve_riot_token_from_user(user_id)
    ent   = get_entitlements(token)
    data  = _pd_get(f"{pd(shard)}/match-details/v1/matches/{match_id}", token, ent)

    if not filter:
        return data

    fields = [f.strip() for f in filter.split(",") if f.strip()]
    if not fields:
        return data

    if len(fields) == 1:
        val = _resolve_path(data, fields[0])
        if val is None:
            raise HTTPException(404, f"Champ introuvable: {fields[0]}")
        return val

    out = {}
    for f in fields:
        val = _resolve_path(data, f)
        if val is not None:
            out[f] = val
    if not out:
        raise HTTPException(404, "Aucun champ demandé trouvé")
    return out


_push_conn = None

def get_push_conn():
    global _push_conn
    if _push_conn is None:
        _push_conn = sqlite3.connect(APP_DB, check_same_thread=False)
        _push_conn.execute("""
        CREATE TABLE IF NOT EXISTS webpush_subscriptions(
          id INTEGER PRIMARY KEY,
          endpoint TEXT UNIQUE NOT NULL,
          p256dh TEXT NOT NULL,
          auth TEXT NOT NULL,
          user_agent TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          last_seen  TEXT
        )""")
        _push_conn.commit()
    return _push_conn

def _push_migrate_add_user_id():
    conn = get_push_conn()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(webpush_subscriptions)")]
    if "user_id" not in cols:
        conn.execute("ALTER TABLE webpush_subscriptions ADD COLUMN user_id TEXT")
        conn.commit()
_push_migrate_add_user_id()

def _push_upsert(endpoint: str, p256dh: str, auth: str, ua: str):
    conn = get_push_conn()
    conn.execute("""
    INSERT INTO webpush_subscriptions(endpoint,p256dh,auth,user_agent,last_seen)
    VALUES(?,?,?,?,?)
    ON CONFLICT(endpoint) DO UPDATE SET
      p256dh=excluded.p256dh, auth=excluded.auth,
      user_agent=excluded.user_agent, last_seen=excluded.last_seen
    """, (endpoint, p256dh, auth, ua, dt.datetime.utcnow().isoformat()))
    conn.commit()
    print(_push_all())

def _push_delete(endpoint: str):
    conn = get_push_conn()
    conn.execute("DELETE FROM webpush_subscriptions WHERE endpoint=?", (endpoint,))
    conn.commit()

def _push_all():
    conn = get_push_conn()
    return conn.execute("SELECT endpoint,p256dh,auth FROM webpush_subscriptions").fetchall()
@app.post("/push/subscribe")
async def push_subscribe(req: Request, user_id: str|None = None):
    sub = await req.json()
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    if not endpoint: raise HTTPException(400, "endpoint manquant")
    _push_upsert(endpoint, keys.get("p256dh",""), keys.get("auth",""),
                 req.headers.get("user-agent",""), user_id)
    return {"ok": True}

@app.post("/push/unsubscribe")
async def push_unsubscribe(req: Request):
    data = await req.json()
    endpoint = data.get("endpoint")
    if not endpoint: raise HTTPException(400, "endpoint manquant")
    _push_delete(endpoint)
    return {"ok": True}
@app.post("/push/attach")
async def push_attach(endpoint: str, user_id: str):
    conn = get_push_conn()
    cur = conn.execute("UPDATE webpush_subscriptions SET user_id=? WHERE endpoint=?", (user_id, endpoint))
    conn.commit()
    return {"ok": cur.rowcount>0}
@app.get("/push/list")
async def push_list(user_id: str):
    conn = get_push_conn()
    rows = conn.execute("""
      SELECT endpoint,p256dh,auth,user_agent,created_at,last_seen
      FROM webpush_subscriptions WHERE user_id=?""", (user_id,)).fetchall()
    return {"count": len(rows), "items": [
        {"endpoint": r[0], "p256dh": r[1], "auth": r[2],
         "user_agent": r[3], "created_at": r[4], "last_seen": r[5]}
    for r in rows]}

@app.post("/push/detach")
async def push_detach(endpoint: str):
    conn = get_push_conn()
    cur = conn.execute("UPDATE webpush_subscriptions SET user_id=NULL WHERE endpoint=?", (endpoint,))
    conn.commit()
    return {"ok": cur.rowcount>0}
from pywebpush import webpush, WebPushException
import json, logging
log = logging.getLogger("webpush")


def _vapid_claims_for(endpoint: str) -> dict:
    """aud = origin de l'endpoint (OK Apple/FCM/Mozilla/…)"""
    u = urlparse(endpoint)
    origin = f"{u.scheme}://{u.netloc}"
    return {"sub": VAPID_SUB, "aud": origin}

# --- broadcast (remplace ton envoi actuel) ---
@app.post("/push/broadcast")
async def push_broadcast(req: Request):
    payload = await req.json()
    msg = json.dumps({
        "title": payload.get("title", "Notif"),
        "body":  payload.get("body", "…"),
        "data":  payload.get("data", {})
    })

    sent = expired = 0
    for endpoint, p256dh, auth in _push_all():
        sub = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
        claims = _vapid_claims_for(endpoint)   # <-- aud correct (ex: https://web.push.apple.com)
        try:
            webpush(
                subscription_info=sub,
                data=msg,
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims=claims,
                ttl=60
            )
            sent += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            body   = getattr(getattr(e, "response", None), "text", None)
            log.warning("webpush fail %s status=%s body=%s", endpoint, status, body)
            if status in (404, 410):   # ne supprime que si expiré
                _push_delete(endpoint)
                expired += 1
    return {"sent": sent, "expired": expired}

@app.get("/push/public-key")
def push_public_key():
    return {"publicKey": VAPID_PUBLIC}


from urllib.parse import urlparse
def _vapid_claims_for(endpoint:str): 
    u = urlparse(endpoint); return {"sub": VAPID_SUB, "aud": f"{u.scheme}://{u.netloc}"}

@app.post("/push/broadcast-to")
async def push_broadcast_to(req: Request, user_id: str):
    payload = await req.json()
    msg = json.dumps({"title": payload.get("title","Notif"),
                      "body": payload.get("body","…"),
                      "data": payload.get("data",{})})
    conn = get_push_conn()
    rows = conn.execute("SELECT endpoint,p256dh,auth FROM webpush_subscriptions WHERE user_id=?", (user_id,)).fetchall()
    sent=expired=0
    for ep,p,a in rows:
        sub={"endpoint":ep,"keys":{"p256dh":p,"auth":a}}
        try:
            webpush(subscription_info=sub, data=msg,
                    vapid_private_key=VAPID_PRIVATE,
                    vapid_claims=_vapid_claims_for(ep), ttl=60)
            sent+=1
        except WebPushException as e:
            status=getattr(getattr(e,"response",None),"status_code",None)
            if status in (404,410):
                _push_delete(ep); expired+=1
    return {"sent":sent,"expired":expired}



from fastapi.responses import StreamingResponse
from typing import Optional, List
from PIL import Image, ImageDraw, ImageFont
import io, json, base64

# --- imports à ajouter en tête du fichier ---
from fastapi import Response
from fastapi.responses import StreamingResponse
from typing import Optional, List
from PIL import Image, ImageDraw, ImageFont
import io, json, base64

def _b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())

def _load_img(url: str, size: tuple[int,int]) -> Image.Image:
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGBA")
        # letterbox dans la box demandée
        im.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0,0,0,0))
        x = (size[0]-im.width)//2
        y = (size[1]-im.height)//2
        canvas.paste(im, (x,y), im)
        return canvas
    except Exception:
        return Image.new("RGBA", size, (0,0,0,0))

def _get_shop_items_for_user(user_id:int) -> List[dict]:
    """Utilise ton cache/flow existant pour lire le featured store d'un user."""
    token = resolve_riot_token_from_user(user_id)
    store = get_front_featured_store(token)  # { offerId: {name: <json skin>, cost: int} }
    items = []
    for offer_id, item in list(store.items())[:4]:
        s = (item.get("name") or {}).get("data") or {}
        items.append({
            "id": offer_id,
            "title": s.get("displayName") or "Skin",
            "price": item.get("cost") or 0,
            "tier": s.get("contentTierUuid") or "",
            "main": s.get("displayIcon") or "",
        })
    return items

def _get_items_from_param(d_param: str) -> List[dict]:
    """Reconstruit à partir d’une liste d’UUID (param d=…) en allant chercher chaque skin."""
    try:
        uuids = json.loads(_b64url_decode(d_param).decode())
        out = []
        for u in uuids[:4]:
            j = get_skin_information(u) or {}
            s = (j.get("data") or {})
            out.append({
                "id": u,
                "title": s.get("displayName") or "Skin",
                "price": int((s.get("know_cost") or 0) or 0),
                "tier": s.get("contentTierUuid") or "",
                "main": s.get("displayIcon") or "",
            })
        return out
    except Exception:
        return []

@app.get("/valorant/shop/image")
def shop_image(user_id: int, d: Optional[str] = None):
    """
    Génère une image PNG de la boutique (2x2).
    - user_id : identifiant de l'utilisateur (table users)
    - d (optionnel) : base64url(JSON des UUID) pour 'shop partagé'
    """
    # 1) Récup données
    items = _get_items_from_param(d) if d else _get_shop_items_for_user(user_id)
    if not items:
        items = [{"title": "Aucune offre", "price": 0, "tier": "", "main": ""}]

    # 2) Mise en page
    W, PADDING, GAP = 1600, 40, 28
    COLS, cardH = 2, 320
    rows = max(1, (len(items) + COLS - 1) // COLS)
    cardW = (W - PADDING * 2 - GAP * (COLS - 1)) // COLS
    H = PADDING * 2 + 120 + rows * cardH + (rows - 1) * GAP

    im = Image.new("RGBA", (W, H), (11, 12, 18, 255))
    draw = ImageDraw.Draw(im)

    # Fond dégradé léger
    for y in range(H):
        a = int(0x12 + (0x2B - 0x12) * y / H)
        draw.line([(0, y), (W, y)], fill=(26, 27, 43, a))

    # Polices
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
        font_sub   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_card  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        font_price = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except Exception:
        font_title = font_sub = font_card = font_price = ImageFont.load_default()

    # Nom joueur
    try:
        token = resolve_riot_token_from_user(user_id)
        puuid = get_player_id(token)
        who = get_user_info(token, [puuid])[0]
        gamer = f"{who.get('GameName','—')}#{who.get('TagLine','—')}"
    except Exception:
        gamer = "Boutique Valorant"

    draw.text((PADDING, PADDING + 4), f"Boutique de {gamer}", font=font_title, fill=(255, 255, 255, 255))
    draw.text((PADDING, PADDING + 58), "Partage généré par VALTrack", font=font_sub, fill=(203, 213, 225, 255))

    # Fonction pour dessiner une card foncée
    def round_rect(x, y, w, h, r=18):
        draw.rounded_rectangle(
            [x, y, x + w, y + h],
            r,
            fill=(20, 20, 30, 255),        # Foncé uniforme
            outline=(255, 255, 255, 40),   # Léger contour clair
            width=1
        )

    # 3) Cartes
    for i, it in enumerate(items):
        r, c = divmod(i, COLS)
        x = PADDING + c * (cardW + GAP)
        y = PADDING + 120 + r * (cardH + GAP)
        round_rect(x, y, cardW, cardH, 18)

        # Titre + prix
        draw.text((x + 18, y + 20), it["title"], font=font_card, fill=(255, 255, 255, 255))
        draw.text((x + 18, y + 50), f"{it['price']:,} VP".replace(",", " "), font=font_price, fill=(203, 213, 225, 255))

        # Tier icon
        if it.get("tier"):
            tier_url = f"https://media.valorant-api.com/contenttiers/{it['tier']}/displayicon.png"
            tier_img = _load_img(tier_url, (40, 40))
            im.alpha_composite(tier_img, dest=(x + cardW - 58, y + 18))

        # Image principale avec fond sombre
        if it.get("main"):
            skin = _load_img(it["main"], (cardW - 36, cardH - 110))
            bg = Image.new("RGBA", (cardW - 36, cardH - 110), (15, 15, 22, 255))
            bx, by = bg.size
            sx, sy = skin.size
            bg.paste(skin, ((bx - sx) // 2, (by - sy) // 2), skin)
            im.alpha_composite(bg, dest=(x + 18, y + 86))

    # 4) Output
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png", headers={"Cache-Control": "public, max-age=60"})
