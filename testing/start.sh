#!/usr/bin/env bash
set -euo pipefail

: "${DISPLAY:=:99}"
: "${SCREEN_WIDTH:=1280}"
: "${SCREEN_HEIGHT:=800}"
: "${SCREEN_DEPTH:=24}"
: "${NO_VNC_PORT:=8080}"
: "${VNC_PORT:=5900}"
: "${ENABLE_REMOTE_SCALING:=1}"

# 1) Xvfb
Xvfb "$DISPLAY" -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH} -dpi 96 &
sleep 0.5

# 2) window manager (léger)
fluxbox &

# 3) x11vnc (sans mot de passe par défaut – à sécuriser en prod)
x11vnc -display "$DISPLAY" -rfbport "$VNC_PORT" -forever -shared -nopw -scale 1x &

# 4) noVNC proxy (avec options utiles mobile)
#   resize : si ENABLE_REMOTE_SCALING=1 -> "scale"
RESIZE_MODE="off"
if [ "$ENABLE_REMOTE_SCALING" = "1" ]; then
  RESIZE_MODE="scale"
fi

# Lien d’accès auto : http://localhost:$NO_VNC_PORT/vnc.html?autoconnect=1&reconnect=1&resize=$RESIZE_MODE
websockify --web=/usr/share/novnc "$NO_VNC_PORT" localhost:"$VNC_PORT" &

# 5) Lancer Firefox sur l’affichage virtuel
export DISPLAY
# Empêche le premier-run dialog
mkdir -p /home/app/.mozilla && chmod -R 700 /home/app/.mozilla
firefox-esr --no-remote --profile /home/app/profile about:blank &

# 6) Wait
wait -n