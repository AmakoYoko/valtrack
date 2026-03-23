# ValTrack — Bug Tracker indépendant (Docker One-Click)

Frontend React + Tailwind, Backend FastAPI, Postgres multi-tenant par schéma, Nginx.  
One-Click : `bash install.sh --up` → http://localhost:8080

## Démarrage

```bash
bash install.sh --up

# Créer un workspace
curl -X POST http://localhost:8080/api/workspaces \
  -H 'Content-Type: application/json' \
  -d '{"name":"Démo","slug":"demo"}'
