FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    SCREEN_WIDTH=1280 \
    SCREEN_HEIGHT=800 \
    SCREEN_DEPTH=24 \
    TZ=Europe/Paris \
    NO_VNC_PORT=8080 \
    VNC_PORT=5900 \
    ENABLE_REMOTE_SCALING=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates tzdata curl xz-utils \
      firefox-esr \
      xvfb x11vnc fluxbox \
      novnc websockify \
      fonts-dejavu fonts-liberation \
      procps \
    && rm -rf /var/lib/apt/lists/*

# noVNC path convenience
ENV NOVNC_DIR=/usr/share/novnc \
    WEBSOCKIFY_CMD=/usr/share/novnc/utils/novnc_proxy

# App user (non-root)
RUN useradd -m -s /bin/bash app
USER app
WORKDIR /home/app

# Profile dir (persistable)
RUN mkdir -p /home/app/profile && mkdir -p /home/app/.vnc

# Startup script
USER root
COPY start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh

# Expose noVNC (HTTP) + VNC (optionnel)
EXPOSE 8080 5900

# Healthcheck : ping Xvfb
HEALTHCHECK CMD pgrep Xvfb >/dev/null || exit 1

USER app
CMD ["/usr/local/bin/start.sh"]