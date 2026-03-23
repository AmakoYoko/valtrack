FROM dorowu/ubuntu-desktop-lxde-vnc:focal

# Optionnel: installer Firefox si absent
RUN apt-get update && apt-get install -y --no-install-recommends firefox-esr && \
    rm -rf /var/lib/apt/lists/*
