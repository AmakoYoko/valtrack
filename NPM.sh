#!/bin/bash

API_URL="https://npm.internal.myplix.eu/api/nginx/proxy-hosts/44"
TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJhcGkiLCJzY29wZSI6WyJ1c2VyIl0sImF0dHJzIjp7ImlkIjoxfSwiZXhwaXJlc0luIjoiMWQiLCJqdGkiOiJqTGlJQ0NTVk1IcjFhNndEIiwiaWF0IjoxNzU1NzgzODU5LCJleHAiOjE3NTU4NzAyNTl9.L29RMKQuvNkaANrrix4DwyXLhN7H9BXztvJb1JD-ZOKb5oCIm-2wGW1KlwEtnff9SV1z16fQ0JW-NYWGOrqz8OpJ6IG6yDhhFlGYg3SYM5txvMUGpzzFfRHZGP_UAa3Pkhmlgf-Af2WKAH76Yhcpq0RUlxPYxxBRBZe9MwiU0k9_LgvxnDaVkDYixwhjyCH9MQQwDOCWakq29FFqMue0cSaTe9U2vh2DLjbMe7Eo-EqmtUCpRZfOcnyGk02kkgT3Y9PTEdmuqfe6Qdt5L4dpaLiB1mC2TQO1iEM_yLrm3tADX_Ly8AvU-dtlup61OsVw1a3EIeCH2sN_NVmENUasiQ" # <-- ton vrai token

# Génération dynamique des locations
locations=$(jq -n '[]')

# riot-auth 52002 → 52022
for port in $(seq 52002 52022); do
  locations=$(echo "$locations" | jq \
    --arg path "/riot-auth/$port" \
    --arg port "$port" \
    '. += [{"path":$path,"advanced_config":"","forward_scheme":"http","forward_host":"192.168.1.137","forward_port":($port|tonumber)}]')
done

# riot-data 53002 → 53022
for port in $(seq 53002 53022); do
  locations=$(echo "$locations" | jq \
    --arg path "/riot-data/$port" \
    --arg port "$port" \
    '. += [{"path":$path,"advanced_config":"","forward_scheme":"http","forward_host":"192.168.1.137","forward_port":($port|tonumber)}]')
done

# Ajout des 3 locations déjà présentes
locations=$(echo "$locations" | jq '. += [
  {"path":"/riot-auth/52001","advanced_config":"","forward_scheme":"http","forward_host":"192.168.1.137","forward_port":52001},
  {"path":"/riot-data/53001","advanced_config":"","forward_scheme":"http","forward_host":"192.168.1.137","forward_port":53001},
  {"path":"/ttest","advanced_config":"","forward_scheme":"http","forward_host":"192.168.1.137","forward_port":80}
]')

# Corps JSON final
data=$(jq -n \
  --argjson locations "$locations" \
  '{
    forward_scheme:"http",
    forward_host:"192.168.1.137",
    forward_port:8000,
    advanced_config:"# tes règles nginx ici...",
    domain_names:["valorant.lamas.one"],
    allow_websocket_upgrade:true,
    access_list_id:"0",
    certificate_id:20,
    ssl_forced:true,
    meta:{letsencrypt_agree:false,dns_challenge:false},
    locations:$locations,
    block_exploits:false,
    caching_enabled:false,
    http2_support:false,
    hsts_enabled:false,
    hsts_subdomains:false
  }')

# Envoi de la requête PUT
curl "$API_URL" \
  -X PUT \
  -H "accept: application/json" \
  -H "authorization: Bearer $TOKEN" \
  -H "content-type: application/json; charset=UTF-8" \
  --data-raw "$data"
