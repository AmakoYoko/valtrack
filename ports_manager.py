import socket, asyncio
from typing import Optional, Tuple

# Plages
WEB_RANGE = range(52002, 52023)   # 52002–52022 inclus
API_RANGE = range(53002, 53023)   # 53002–53022 inclus

# État mémoire (évite collisions entre requêtes simultanées)
_alloc_web: set[int] = set()
_alloc_api: set[int] = set()
_lock = asyncio.Lock()

def _is_port_free(p: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", p))
            return True
        except OSError:
            return False

def _find_free_in(pool: range, already: set[int]) -> Optional[int]:
    for p in pool:
        if p in already:
            continue
        if _is_port_free(p):
            return p
    return None

async def pick_login_ports() -> dict:
    """
    Retourne:
      - {"ok": True,  "web_port": X, "api_port": Y}
      - {"ok": False, "reason": "NO_CAPACITY", "retry_after": 15}
    """
    async with _lock:
        wp = _find_free_in(WEB_RANGE, _alloc_web)
        ap = _find_free_in(API_RANGE, _alloc_api)
        if wp is None or ap is None:
            return {"ok": False, "reason": "NO_CAPACITY", "retry_after": 15}

        # Réservation mémoire (libérer quand le conteneur s'arrête ou si échec)
        _alloc_web.add(wp)
        _alloc_api.add(ap)
        return {"ok": True, "web_port": wp, "api_port": ap}

async def release_login_ports(web_port: int, api_port: int) -> None:
    async with _lock:
        _alloc_web.discard(web_port)
        _alloc_api.discard(api_port)