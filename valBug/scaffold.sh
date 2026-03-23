#!/usr/bin/env bash
# scaffold.sh — génère le projet ValTrack complet
set -euo pipefail

DIR="${1:-valtrack}"
mkdir -p "$DIR"
cd "$DIR"

echo "[1/7] Création des dossiers…"
mkdir -p backend/app/routes frontend/src/pages frontend/src/components

echo "[2/7] Fichiers racine…"

cat > .env.example <<'EOF'
# ====== CORE ======
COMPOSE_PROJECT_NAME=valtrack
TZ=Europe/Paris

# ====== POSTGRES ======
POSTGRES_USER=valtrack
POSTGRES_PASSWORD=change-me
POSTGRES_DB=valtrack
POSTGRES_HOST=db
POSTGRES_PORT=5432
DATABASE_URL=postgresql+psycopg2://valtrack:change-me@db:5432/valtrack

# ====== API ======
SECRET_KEY=please-change-this
ACCESS_TOKEN_EXPIRE_MINUTES=43200
ALLOWED_ORIGINS=http://localhost:8080,http://localhost

# ====== FRONTEND ======
PUBLIC_API_BASE=/api
PUBLIC_BRAND=ValTrack

# ====== FIRST ADMIN (créé au 1er boot si absent) ======
ADMIN_EMAIL=admin@local
ADMIN_PASSWORD=adminadmin
EOF

cat > docker-compose.yml <<'EOF'
version: "3.9"
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      TZ: ${TZ}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"]
      interval: 5s
      timeout: 5s
      retries: 20

  api:
    build: ./backend
    environment:
      DATABASE_URL: ${DATABASE_URL}
      SECRET_KEY: ${SECRET_KEY}
      ACCESS_TOKEN_EXPIRE_MINUTES: ${ACCESS_TOKEN_EXPIRE_MINUTES}
      ALLOWED_ORIGINS: ${ALLOWED_ORIGINS}
      ADMIN_EMAIL: ${ADMIN_EMAIL}
      ADMIN_PASSWORD: ${ADMIN_PASSWORD}
      TZ: ${TZ}
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 10s
      timeout: 5s
      retries: 20

  web:
    build: ./frontend
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "8080:80"
    environment:
      PUBLIC_API_BASE: ${PUBLIC_API_BASE}
      PUBLIC_BRAND: ${PUBLIC_BRAND}

volumes:
  pgdata:
EOF

cat > install.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

has() { command -v "$1" &>/dev/null; }

if ! has docker; then echo "[!] Docker n'est pas installé"; exit 1; fi
if ! docker compose version &>/dev/null; then echo "[!] docker compose plugin requis"; exit 1; fi
if ! has openssl; then echo "[!] openssl requis"; exit 1; fi
if ! has sed; then echo "[!] sed requis"; exit 1; fi

cp -n .env.example .env || true

# Génère des secrets si les valeurs sont par défaut
if grep -q "^SECRET_KEY=please-change-this" .env; then
  sed -i "s/SECRET_KEY=please-change-this/SECRET_KEY=$(openssl rand -hex 32)/" .env
fi

PGPASS=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)
if [ "$PGPASS" = "change-me" ]; then
  NEWPASS=$(openssl rand -hex 16)
  sed -i "s/POSTGRES_PASSWORD=change-me/POSTGRES_PASSWORD=${NEWPASS}/" .env
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+psycopg2://valtrack:${NEWPASS}@db:5432/valtrack|" .env
fi

ACTION=${1:---up}
case "$ACTION" in
  --up)
    docker compose pull
    docker compose build --pull
    docker compose up -d
    echo ""
    echo "[✓] ValTrack lancé : http://localhost:8080"
    echo "    API: http://localhost:8080/api  | Health: /api/healthz"
    echo "    Admin par défaut: $(grep '^ADMIN_EMAIL=' .env | cut -d= -f2) / $(grep '^ADMIN_PASSWORD=' .env | cut -d= -f2)"
    ;;
  --down)
    docker compose down
    ;;
  --rebuild)
    docker compose build --no-cache
    docker compose up -d
    ;;
  *)
    echo "Usage: bash install.sh [--up|--down|--rebuild]"
    exit 1
    ;;
esac
EOF
chmod +x install.sh

echo "[3/7] Backend…"

cat > backend/Dockerfile <<'EOF'
FROM python:3.10-slim as base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

cat > backend/requirements.txt <<'EOF'
fastapi==0.112.2
uvicorn[standard]==0.30.6
SQLAlchemy==1.4.54
psycopg2-binary==2.9.9
pydantic==2.8.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
EOF

cat > backend/app/db.py <<'EOF'
from contextlib import contextmanager
from typing import Generator, Optional
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

PUBLIC_SEARCH_PATH = 'public'

@contextmanager
def workspace_session(schema: Optional[str]) -> Generator:
    """Yield a session with search_path set to the workspace schema (or public)."""
    session = SessionLocal()
    try:
        sp = schema or PUBLIC_SEARCH_PATH
        session.execute(text("SET search_path TO :sp"), {"sp": sp})
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
EOF

cat > backend/app/models_meta.py <<'EOF'
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Boolean, DateTime, func
import uuid

MetaBase = declarative_base()

def gen_uuid():
    return str(uuid.uuid4())

class User(MetaBase):
    __tablename__ = 'users'
    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Workspace(MetaBase):
    __tablename__ = 'workspaces'
    id = Column(String, primary_key=True, default=gen_uuid)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    created_by = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
EOF

cat > backend/app/models_ws.py <<'EOF'
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, DateTime, func, Text, ForeignKey
import uuid

WSBase = declarative_base()

def gen_uuid():
    return str(uuid.uuid4())

class Issue(WSBase):
    __tablename__ = 'issues'
    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default='open')  # open, in_progress, closed
    priority = Column(String, default='normal')  # low, normal, high, urgent
    reporter_id = Column(String, nullable=True)
    assignee_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Comment(WSBase):
    __tablename__ = 'comments'
    id = Column(String, primary_key=True, default=gen_uuid)
    issue_id = Column(String, ForeignKey('issues.id', ondelete='CASCADE'), index=True)
    author_id = Column(String)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
EOF

cat > backend/app/schemas.py <<'EOF'
from pydantic import BaseModel, EmailStr
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class WorkspaceCreate(BaseModel):
    name: str
    slug: str

class WorkspaceOut(BaseModel):
    id: str
    name: str
    slug: str

class IssueCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: Optional[str] = 'normal'

class IssueOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class CommentCreate(BaseModel):
    issue_id: str
    body: str

class CommentOut(BaseModel):
    id: str
    issue_id: str
    body: str
    created_at: Optional[str] = None
EOF

cat > backend/app/auth.py <<'EOF'
import os
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from .models_meta import User

SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret')
ALGO = 'HS256'
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '60'))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)

def verify_password(p: str, h: str) -> bool:
    return pwd_ctx.verify(p, h)

def create_token(user_id: str) -> str:
    exp = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": exp}, SECRET_KEY, algorithm=ALGO)

async def get_user_by_email(session, email: str):
    q = await session.execute(select(User).where(User.email == email))
    return q.scalar_one_or_none()
EOF

cat > backend/app/utils.py <<'EOF'
from sqlalchemy import text
from .models_ws import WSBase

WS_PREFIX = 'ws_'

def schema_name_from_slug(slug: str) -> str:
    s = slug.lower().replace(' ', '-')
    safe = ''.join(c for c in s if c.isalnum() or c in ('-', '_'))
    safe = safe.replace('-', '_')
    return WS_PREFIX + safe

async def ensure_workspace_schema(session, schema: str):
    session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    session.execute(text("SET search_path TO :sp"), {"sp": schema})
    WSBase.metadata.create_all(bind=session.get_bind())
EOF

cat > backend/app/routes/auth.py <<'EOF'
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from ..db import workspace_session
from ..models_meta import User
from ..auth import verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginBody(BaseModel):
    email: str
    password: str

@router.post('/login')
async def login(body: LoginBody):
    with workspace_session('public') as s:
        q = s.execute(select(User).where(User.email == body.email))
        user = q.scalar_one_or_none()
        if not user or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"access_token": create_token(user.id), "token_type": "bearer"}
EOF

cat > backend/app/routes/workspaces.py <<'EOF'
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from ..db import workspace_session
from ..schemas import WorkspaceCreate, WorkspaceOut
from ..models_meta import Workspace
from ..utils import schema_name_from_slug, ensure_workspace_schema

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

@router.post('', response_model=WorkspaceOut)
async def create_workspace(body: WorkspaceCreate):
    schema = schema_name_from_slug(body.slug)
    with workspace_session('public') as s:
        exists = s.execute(select(Workspace).where(Workspace.slug == body.slug)).scalar_one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail="Slug already exists")
        ws = Workspace(name=body.name, slug=body.slug)
        s.add(ws)
        s.flush()
        await ensure_workspace_schema(s, schema)
        return WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug)

@router.get('', response_model=list[WorkspaceOut])
async def list_workspaces():
    with workspace_session('public') as s:
        rows = s.execute(select(Workspace)).scalars().all()
        return [WorkspaceOut(id=w.id, name=w.name, slug=w.slug) for w in rows]
EOF

cat > backend/app/routes/issues.py <<'EOF'
from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select
from ..db import workspace_session
from ..schemas import IssueCreate, IssueOut, CommentCreate, CommentOut
from ..models_ws import Issue, Comment

router = APIRouter(prefix="/issues", tags=["issues"])

def _schema_from_headers(x_workspace: str | None, x_workspace_id: str | None) -> str:
    if not x_workspace and not x_workspace_id:
        raise HTTPException(status_code=400, detail="X-Workspace or X-Workspace-ID required")
    if x_workspace:
        from ..utils import schema_name_from_slug
        return schema_name_from_slug(x_workspace)
    return f"ws_{x_workspace_id}"

@router.post('', response_model=IssueOut)
async def create_issue(
    body: IssueCreate,
    X_Workspace: str | None = Header(default=None),
    X_Workspace_ID: str | None = Header(default=None)
):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session(schema) as s:
        issue = Issue(title=body.title, description=body.description, priority=body.priority)
        s.add(issue)
        s.flush()
        return IssueOut(
            id=issue.id, title=issue.title, description=issue.description,
            status=issue.status, priority=issue.priority, created_at=str(issue.created_at)
        )

@router.get('', response_model=list[IssueOut])
async def list_issues(
    status: str | None = None,
    X_Workspace: str | None = Header(default=None),
    X_Workspace_ID: str | None = Header(default=None)
):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session(schema) as s:
        q = select(Issue)
        if status:
            q = q.where(Issue.status == status)
        rows = s.execute(q).scalars().all()
        return [
            IssueOut(
                id=r.id, title=r.title, description=r.description,
                status=r.status, priority=r.priority,
                created_at=str(r.created_at),
                updated_at=str(r.updated_at) if r.updated_at else None
            ) for r in rows
        ]

@router.get('/{issue_id}', response_model=IssueOut)
async def get_issue(
    issue_id: str,
    X_Workspace: str | None = Header(default=None),
    X_Workspace_ID: str | None = Header(default=None)
):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session(schema) as s:
        row = s.get(Issue, issue_id)
        if not row:
            raise HTTPException(status_code=404, detail="Issue not found")
        return IssueOut(
            id=row.id, title=row.title, description=row.description,
            status=row.status, priority=row.priority,
            created_at=str(row.created_at),
            updated_at=str(row.updated_at) if row.updated_at else None
        )

@router.post('/comments', response_model=CommentOut)
async def add_comment(
    body: CommentCreate,
    X_Workspace: str | None = Header(default=None),
    X_Workspace_ID: str | None = Header(default=None)
):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session(schema) as s:
        c = Comment(issue_id=body.issue_id, body=body.body)
        s.add(c)
        s.flush()
        return CommentOut(id=c.id, issue_id=c.issue_id, body=c.body, created_at=str(c.created_at))
EOF

cat > backend/app/main.py <<'EOF'
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
EOF

echo "[4/7] Frontend…"

cat > frontend/Dockerfile <<'EOF'
# Build stage
FROM node:20-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Serve stage
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
EOF

cat > frontend/nginx.conf <<'EOF'
server {
  listen 80;
  server_name _;

  root /usr/share/nginx/html;
  index index.html;

  location /api/ {
    proxy_pass http://api:8000/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location / {
    try_files $uri /index.html;
  }
}
EOF

cat > frontend/package.json <<'EOF'
{
  "name": "valtrack-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview --port 8080"
  },
  "dependencies": {
    "axios": "^1.7.2",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.40",
    "tailwindcss": "^3.4.10",
    "vite": "^5.4.2",
    "@vitejs/plugin-react": "^4.3.1"
  }
}
EOF

cat > frontend/vite.config.js <<'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})
EOF

cat > frontend/index.html <<'EOF'
<!doctype html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ValTrack — Bug Tracker</title>
  <script>
    window.__ENV__ = {
      PUBLIC_API_BASE: (new URLSearchParams(location.search).get('api')) || ("/api"),
      PUBLIC_BRAND: "ValTrack"
    }
  </script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: ui-sans-serif, system-ui, Inter, Segoe UI, Roboto; }
  </style>
</head>
<body class="bg-zinc-950 text-zinc-100">
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
EOF

cat > frontend/src/api.js <<'EOF'
import axios from 'axios'

const API_BASE = (window.__ENV__ && window.__ENV__.PUBLIC_API_BASE) || '/api'

export const api = axios.create({
  baseURL: API_BASE,
})

export function setWorkspaceHeader(slug){
  api.defaults.headers.common['X-Workspace'] = slug
}
EOF

cat > frontend/src/main.jsx <<'EOF'
import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

createRoot(document.getElementById('root')).render(<App />)
EOF

cat > frontend/src/App.jsx <<'EOF'
import React, { useEffect, useState } from 'react'
import Layout from './components/Layout'
import IssuesList from './pages/IssuesList'
import NewIssue from './pages/NewIssue'
import IssueDetail from './pages/IssueDetail'

export default function App(){
  const [route, setRoute] = useState(window.location.hash.slice(1) || 'issues')
  useEffect(()=>{
    const onHash = () => setRoute(window.location.hash.slice(1) || 'issues')
    window.addEventListener('hashchange', onHash)
    return ()=> window.removeEventListener('hashchange', onHash)
  }, [])

  let page = <IssuesList/>
  if(route.startsWith('new')) page = <NewIssue/>
  if(route.startsWith('issue/')) page = <IssueDetail id={route.split('/')[1]} />

  return <Layout onNavigate={(r)=>location.hash = r}>{page}</Layout>
}
EOF

cat > frontend/src/components/Layout.jsx <<'EOF'
import React, { useEffect } from 'react'
import Topbar from './Topbar'

export default function Layout({children, onNavigate}){
  useEffect(()=>{ document.title = (window.__ENV__?.PUBLIC_BRAND || 'ValTrack') + ' — Bug Tracker' }, [])
  return (
    <div className="min-h-screen">
      <Topbar onNavigate={onNavigate} />
      <main className="max-w-5xl mx-auto p-4 md:p-8 space-y-6">{children}</main>
    </div>
  )
}
EOF

cat > frontend/src/components/Topbar.jsx <<'EOF'
import React, { useEffect, useState } from 'react'
import { api, setWorkspaceHeader } from '../api'

export default function Topbar({onNavigate}){
  const [workspaces,setWorkspaces] = useState([])
  const [current,setCurrent] = useState('demo')

  useEffect(()=>{
    api.get('/workspaces').then(r=> setWorkspaces(r.data)).catch(()=>{})
  }, [])

  useEffect(()=>{ setWorkspaceHeader(current) }, [current])

  return (
    <header className="border-b border-white/10 bg-zinc-950/60 backdrop-blur sticky top-0 z-10">
      <div className="max-w-5xl mx-auto flex items-center gap-4 p-3">
        <div className="font-extrabold text-xl">{window.__ENV__?.PUBLIC_BRAND || 'ValTrack'}</div>
        <nav className="flex items-center gap-2 text-sm">
          <a className="px-3 py-1 rounded-lg hover:bg-white/10" onClick={()=>onNavigate('issues')}>Issues</a>
          <a className="px-3 py-1 rounded-lg hover:bg-white/10" onClick={()=>onNavigate('new')}>Nouvelle issue</a>
        </nav>
        <div className="ml-auto">
          <select className="bg-zinc-900 border border-white/10 rounded-lg px-3 py-1" value={current} onChange={e=>setCurrent(e.target.value)}>
            <option value="demo">demo</option>
            {workspaces.map(w=> <option key={w.id} value={w.slug}>{w.name}</option>)}
          </select>
        </div>
      </div>
    </header>
  )
}
EOF

cat > frontend/src/components/IssueCard.jsx <<'EOF'
import React from 'react'

export default function IssueCard({issue, onClick}){
  const badge = {
    open: 'bg-emerald-500/20 text-emerald-300',
    in_progress: 'bg-amber-500/20 text-amber-300',
    closed: 'bg-zinc-500/20 text-zinc-300'
  }[issue.status] || 'bg-zinc-700/20 text-zinc-300'

  return (
    <div onClick={onClick} className="p-4 rounded-2xl border border-white/10 bg-white/5 hover:bg-white/10 transition cursor-pointer">
      <div className="flex items-center gap-3">
        <span className={`text-xs px-2 py-0.5 rounded-full ${badge}`}>{issue.status}</span>
        <h3 className="font-semibold text-lg">{issue.title}</h3>
        <span className="ml-auto text-xs text-zinc-400">prio: {issue.priority}</span>
      </div>
      {issue.description && <p className="text-zinc-300 mt-2 line-clamp-2">{issue.description}</p>}
    </div>
  )
}
EOF

cat > frontend/src/pages/IssuesList.jsx <<'EOF'
import React, { useEffect, useState } from 'react'
import { api } from '../api'
import IssueCard from '../components/IssueCard'

export default function IssuesList(){
  const [items,setItems] = useState(null)
  useEffect(()=>{ api.get('/issues').then(r=> setItems(r.data)) }, [])
  if(!items) return <div className="animate-pulse text-zinc-400">Chargement…</div>
  return (
    <div className="space-y-3">
      {items.map(i=> <IssueCard key={i.id} issue={i} onClick={()=> location.hash = `issue/${i.id}`} />)}
      {items.length===0 && <div className="text-zinc-400">Aucune issue pour l’instant.</div>}
    </div>
  )
}
EOF

cat > frontend/src/pages/NewIssue.jsx <<'EOF'
import React, { useState } from 'react'
import { api } from '../api'

export default function NewIssue(){
  const [title,setTitle] = useState('')
  const [description,setDescription] = useState('')
  const [priority,setPriority] = useState('normal')
  const submit = async (e)=>{
    e.preventDefault()
    await api.post('/issues', {title, description, priority})
    location.hash = 'issues'
  }
  return (
    <form onSubmit={submit} className="max-w-xl space-y-3">
      <input className="w-full bg-zinc-900 border border-white/10 rounded-xl p-3" placeholder="Titre" value={title} onChange={e=>setTitle(e.target.value)} />
      <textarea className="w-full bg-zinc-900 border border-white/10 rounded-xl p-3" rows="6" placeholder="Description" value={description} onChange={e=>setDescription(e.target.value)} />
      <div className="flex gap-2 items-center">
        <label>Priorité</label>
        <select className="bg-zinc-900 border border-white/10 rounded-lg px-3 py-2" value={priority} onChange={e=>setPriority(e.target.value)}>
          <option value="low">Basse</option>
          <option value="normal">Normale</option>
          <option value="high">Haute</option>
          <option value="urgent">Urgente</option>
        </select>
      </div>
      <button className="bg-white text-black font-semibold px-4 py-2 rounded-xl">Créer</button>
    </form>
  )
}
EOF

cat > frontend/src/pages/IssueDetail.jsx <<'EOF'
import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function IssueDetail({id}){
  const [issue,setIssue] = useState(null)
  const [comment,setComment] = useState('')
  useEffect(()=>{ api.get(`/issues/${id}`).then(r=> setIssue(r.data)) }, [id])
  if(!issue) return <div className="animate-pulse text-zinc-400">Chargement…</div>
  const add = async ()=>{ await api.post('/issues/comments', {issue_id:id, body:comment}); setComment(''); location.reload() }
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-2xl border border-white/10 bg-white/5">
        <h2 className="text-2xl font-bold">{issue.title}</h2>
        <p className="text-zinc-300 mt-2 whitespace-pre-wrap">{issue.description || '—'}</p>
      </div>
      <div className="p-4 rounded-2xl border border-white/10 bg-white/5">
        <h3 className="font-semibold mb-2">Ajouter un commentaire</h3>
        <div className="flex gap-2">
          <input value={comment} onChange={e=>setComment(e.target.value)} className="flex-1 bg-zinc-900 border border-white/10 rounded-xl p-3" placeholder="Votre message…" />
          <button onClick={add} className="bg-white text-black font-semibold px-4 py-2 rounded-xl">Envoyer</button>
        </div>
      </div>
    </div>
  )
}
EOF

echo "[5/7] README…"
cat > README.md <<'EOF'
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
EOF

echo "[6/7] Permissions…"
chmod +x install.sh

echo "[7/7] Terminé ✅"
echo
echo "Prochaines étapes :"
echo " cd $(pwd)"
echo " bash install.sh --up"
echo "Puis ouvre: http://localhost:8080"