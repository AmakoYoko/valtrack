#!/usr/bin/env bash
sleep 1
firefox --no-remote --new-instance \
  "https://auth.riotgames.com/authorize?client_id=play-valorant-web-prod&nonce=1&redirect_uri=https://playvalorant.com/opt_in&response_type=token%20id_token" &
