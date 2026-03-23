#!/bin/sh
APP_DB=app.db python3 -m uvicorn riot_auth_manager:app \
  --host 0.0.0.0 --port 8000 --workers 1 --reload &
