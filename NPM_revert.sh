#!/usr/bin/env bash
set -euo pipefail

# === À adapter ===
NPM_URL="https://npm.internal.myplix.eu/"
NPM_USER="laura.pinto@lamas.one"
NPM_PASS="@Dfujbx123"

# Optionnel : ajoute -k à CURL si ton NPM a un cert non fiable
CURL="curl -sS"

echo ">> Auth..."
TOKEN=$($CURL -X POST "${NPM_URL%/}/api/tokens" \
  -H "Content-Type: application/json" \
  -d "{\"identity\":\"$NPM_USER\",\"secret\":\"$NPM_PASS\"}" | jq -r .token)

if [[ -z "${TOKEN:-}" || "$TOKEN" == "null" ]]; then
  echo "❌ Impossible d'obtenir le token API"; exit 1
fi

echo ">> Récupération des hosts..."
HOSTS_JSON=$($CURL -H "Authorization: Bearer $TOKEN" "${NPM_URL%/}/api/nginx/proxy-hosts")

delete_host() {
  local domain="$1"
  local id
  id=$(echo "$HOSTS_JSON" | jq -r --arg d "$domain" '.[] | select(.domain_names[]?==$d) | .id' | head -n1)
  if [[ -n "${id:-}" && "$id" != "null" ]]; then
    $CURL -X DELETE "${NPM_URL%/}/api/nginx/proxy-hosts/$id" \
      -H "Authorization: Bearer $TOKEN" >/dev/null
    echo "✓ Deleted $domain (id=$id)"
  else
    echo "· Not found $domain"
  fi
}

# auth1..auth10
for i in $(seq 1 10); do
  delete_host "auth$i.valorant.lamas.one"
done

# auth_data1..auth_data10
for i in $(seq 1 10); do
  delete_host "auth_data$i.valorant.lamas.one"
done

echo ">> Terminé."
