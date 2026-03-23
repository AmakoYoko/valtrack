import os
from uuid import uuid4
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .db import engine, workspace_session
from .models_meta import MetaBase
from .auth import hash_password
from .routes import auth as auth_routes
from .routes import workspaces as ws_routes
from .routes import issues as issues_routes

ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')

app = FastAPI(title="ValTrack API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    # Create meta tables in public
    MetaBase.metadata.create_all(bind=engine)
    # Create first admin if missing
    admin_email = os.getenv('ADMIN_EMAIL')
    admin_password = os.getenv('ADMIN_PASSWORD')
    if admin_email and admin_password:
        with workspace_session('public') as s:
            exists = s.execute(text("SELECT 1 FROM users WHERE email=:e"), {"e": admin_email}).first()
            if not exists:
                s.execute(
                    text("INSERT INTO users(id,email,password_hash,is_active) VALUES (:id,:e,:p,true)"),
                    {"id": str(uuid4()), "e": admin_email, "p": hash_password(admin_password)}
                )

@app.get('/healthz')
async def healthz():
    return {"ok": True}

app.include_router(auth_routes.router)
app.include_router(ws_routes.router)
app.include_router(issues_routes.router)
