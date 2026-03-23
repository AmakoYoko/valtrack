FROM debian:bullseye

ENV DEBIAN_FRONTEND=noninteractive \
    EXT_ID=riot@local \
    PROFILE_DIR=/root/.mozilla/firefox/riotprofile \
    XPRA_HTML=/opt/xpra-www

# Dépendances
RUN apt-get update && apt-get install -y --no-install-recommends \
    xpra xauth x11-utils x11-xserver-utils \
    xvfb xserver-xorg-core xserver-xorg-video-dummy xserver-xorg-legacy \
    pulseaudio dbus fluxbox firefox-esr python3 python3-pip curl wget speech-dispatcher \

 && rm -rf /var/lib/apt/lists/*

# Autoriser Xorg “legacy” sans tty (container)
RUN printf "allowed_users=anybody\nneeds_root_rights=yes\n" > /etc/Xorg.wrap

RUN pip install pillow flask
# Extension + scripts
COPY riot_token_extractor /riot_token_extension/
COPY forward_debugger.py /forward_debugger.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Profil Firefox avec extension
RUN mkdir -p ${PROFILE_DIR}/extensions ${PROFILE_DIR}/chrome && \
    cp -r /riot_token_extension ${PROFILE_DIR}/extensions/${EXT_ID} && \
    printf "[Profile0]\nName=riotprofile\nIsRelative=1\nPath=riotprofile\nDefault=1\n" > /root/.mozilla/firefox/profiles.ini

RUN cat > ${PROFILE_DIR}/user.js <<'EOF'
user_pref("xpinstall.signatures.required", false);
user_pref("extensions.autoDisableScopes", 0);
user_pref("extensions.enabledScopes", 15);
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
user_pref("devtools.policy.disabled", true);
user_pref("media.webspeech.synth.enabled", false);
EOF

RUN cat > ${PROFILE_DIR}/chrome/userContent.css <<'EOF'
.osano-cm-window__dialog.osano-cm-dialog.osano-cm-dialog--position_bottom.osano-cm-dialog--type_bar {
  display:none !important;
}
EOF

# politique Firefox (désactive devtools côté policies)
RUN mkdir -p /usr/lib/firefox-esr/distribution && \
    printf '{ "policies": { "DisableDeveloperTools": true } }\n' \
      > /usr/lib/firefox-esr/distribution/policies.json


# Webroot HTML5 Xpra avec override CSS + hack clavier mobile
RUN mkdir -p ${XPRA_HTML} && \
    cp -r /usr/share/xpra/www/* ${XPRA_HTML}/ && \
    printf '#float_menu { display: none !important; } .notifications{display:none !important;}\n' > ${XPRA_HTML}/custom.css && \
    sed -i 's#</head>#<link rel="stylesheet" href="custom.css?t=123"></head>#' ${XPRA_HTML}/index.html && \
    sed -i 's#</body>#<input id="ime-hack" style="position:absolute;top:-100px" /><script>document.addEventListener("touchstart",function(){var e=document.getElementById("ime-hack");if(e){e.focus();}});</script></body>#' ${XPRA_HTML}/index.html

EXPOSE 10000 5000
CMD ["/start.sh"]
