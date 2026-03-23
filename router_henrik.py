# --- router_henrik.py --------------------------------------------------------
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Tuple, Any, List
import time, urllib.parse, httpx, asyncio

router = APIRouter(prefix="/henrik", tags=["henrik"])
HENRIK_KEYS: List[str] = [
    "HDEV-5b3bb495-aaf6-4ba2-8723-b8f94574c0aa",  # <-- remplace
    "HDEV-e307b637-e30b-45d3-9000-ba3864fe2dd2"  # <-- remplace
]

# ---- Soft rate-limit par clé (window rolling simple) ----
RPM_PER_KEY = 30           # ajuste si tu as le palier Advanced (ex: 90)
WINDOW_SEC = 60
_key_state = {k: {"count": 0, "window_start": 0.0} for k in HENRIK_KEYS}
_key_index = 0

# ---- Cache mémoire simple ----
CACHE_TTL = 30  
_cache: Dict[str, Tuple[float, Any]] = {}

def _cache_get(k: str):
    item = _cache.get(k)
    if not item: return None
    exp, data = item
    if exp < time.time():
        _cache.pop(k, None)
        return None
    return data

def _cache_set(k: str, data: Any, ttl: int = CACHE_TTL):
    _cache[k] = (time.time() + ttl, data)

def _pick_key() -> str:
    """Round-robin avec respect RPM par clé; si fenêtre expirée -> reset."""
    global _key_index
    now = time.time()
    for _ in range(len(HENRIK_KEYS)):
        k = HENRIK_KEYS[_key_index]
        st = _key_state[k]
        if now - st["window_start"] >= WINDOW_SEC:
            st["window_start"] = now
            st["count"] = 0
        if st["count"] < RPM_PER_KEY:
            _key_index = (_key_index + 1) % len(HENRIK_KEYS)
            st["count"] += 1
            return k
        _key_index = (_key_index + 1) % len(HENRIK_KEYS)
    # toutes saturées -> on lève 429 côté app (à toi de retry côté client)
    raise HTTPException(status_code=429, detail="Rate limit (keys busy)")

async def _henrik_get(path: str, ttl: int = CACHE_TTL):
    base = "https://api.henrikdev.xyz"
    url = f"{base}{path}"
    if (cached := _cache_get(url)) is not None:
        return cached
    # tentative avec 2 clés max (bascule si 429/403)
    last_error = None
    for _ in range(len(HENRIK_KEYS)):
        key = _pick_key()
        try:
            async with httpx.AsyncClient(timeout=10) as cli:
                r = await cli.get(url, headers={"Authorization": key})
            if r.status_code == 200:
                data = r.json()
                _cache_set(url, data, ttl=ttl)
                return data
            if r.status_code in (429, 403):
                last_error = r
                # on essaie la clé suivante
                continue
            # autres erreurs renvoyées telles quelles
            raise HTTPException(status_code=r.status_code, detail=r.text)
        except HTTPException:
            raise
        except Exception as e:
            last_error = e
            continue
    # si on arrive ici: toutes les clés ont échoué
    if isinstance(last_error, httpx.Response):
        raise HTTPException(status_code=last_error.status_code, detail=last_error.text)
    raise HTTPException(status_code=502, detail=f"Henrik upstream error: {last_error}")

def _enc(s: str) -> str:
    return urllib.parse.quote(s, safe="")

# ------------------ Endpoints pratiques ------------------

@router.get("/account/{name}/{tag}")
async def get_account(name: str, tag: str):
    path = f"/valorant/v1/account/{_enc(name)}/{_enc(tag)}"
    # infos de base: puuid, region, level, card, title, etc.
    return await _henrik_get(path, ttl=300)

@router.get("/mmr/{region}/{name}/{tag}")
async def get_mmr(region: str, name: str, tag: str):
    path = f"/valorant/v2/mmr/{_enc(region)}/{_enc(name)}/{_enc(tag)}"
    return await _henrik_get(path, ttl=60)

@router.get("/matches/{region}/{name}/{tag}")
async def get_matches(
    region: str, name: str, tag: str,
    size: int = Query(10, ge=1, le=50),
    platform: str = Query("pc", regex="^(pc|console)$")
):
    path = f"/valorant/v4/matches/{_enc(region)}/{_enc(platform)}/{_enc(name)}/{_enc(tag)}?size={size}"
    return await _henrik_get(path, ttl=20)

# (optionnel) pass-through générique si besoin:
@router.get("/raw")
async def passthrough(path: str):
    if not path.startswith("/valorant/"):
        raise HTTPException(400, "path must start with /valorant/")
    return await _henrik_get(path, ttl=15)
# router_henrik.py (complément)
@router.get("/account/by-puuid/{puuid}")
async def get_account_by_puuid(puuid: str):
    path = f"/valorant/v1/by-puuid/account/{urllib.parse.quote(puuid, safe='')}"
    return await _henrik_get(path, ttl=300)
