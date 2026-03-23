#!/bin/bash
set -e
export DISPLAY=:10

python3 /forward_debugger.py &

PROFILE_DIR="/root/.mozilla/firefox/riotprofile"
EXT_ID="riot@local"

# Crée le profil + prefs
if [ ! -d "$PROFILE_DIR" ]; then
  mkdir -p "$PROFILE_DIR"/{extensions,chrome}
  cat > /root/.mozilla/firefox/profiles.ini <<EOF
[Profile0]
Name=riotprofile
IsRelative=1
Path=riotprofile
Default=1
EOF

  # Prefs
  cat > "$PROFILE_DIR/user.js" <<'EOF'
  user_pref("media.webspeech.synth.enabled", false); user_pref("xpinstall.signatures.required", false);user_pref("extensions.autoDisableScopes", 0);user_pref("extensions.enabledScopes", 15);user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);user_pref("devtools.policy.disabled", true);user_pref("media.webspeech.synth.enabled", false);
EOF

  # Extension
  cp -r /riot_token_extension "$PROFILE_DIR/extensions/$EXT_ID"

  # CSS contenu (masque OSANO)
  cat > "$PROFILE_DIR/chrome/userContent.css" <<'EOF'
.osano-cm-window__dialog.osano-cm-dialog.osano-cm-dialog--position_bottom.osano-cm-dialog--type_bar{
  display:none !important;
}
EOF

  # CSS chrome (masque l’infobar speech)
  cat > "$PROFILE_DIR/chrome/userChrome.css" <<'EOF'
/* divers notifs */
#notification-popup, .global-notificationbox, .browser-notificationbox { display:none !important; }
/* cible spécifique speech (selon versions) */
notification[value="speechsynth"], notification[value="speech-synth"] { display:none !important; }
EOF
fi

# supprime les locks
rm -f "$PROFILE_DIR"/parent.lock "$PROFILE_DIR"/.parentlock

# Lance Xpra + Firefox (attention: --www, pas --html=path)
xpra start :10 \
  --bind-tcp=0.0.0.0:10000 \
  --daemon=no \
  --xvfb="Xvfb" \
  --resize-display=yes \
  --desktop-scaling=auto \
  --html="/opt/xpra-www" \
  --notifications=no \
  --pulseaudio=no --dbus-proxy=no \
  --exit-with-children \
  --start-child="fluxbox" \
  --start-child="firefox-esr --no-remote --new-instance --kiosk \
    --width 412 --height 915 -profile $PROFILE_DIR \
    'https://auth.riotgames.com/authorize?client_id=play-valorant-web-prod&nonce=1&redirect_uri=https://playvalorant.com/opt_in&response_type=token%20id_token'"
