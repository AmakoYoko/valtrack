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
        ensure_workspace_schema(s, schema)
        return WorkspaceOut(id=ws.id, name=ws.name, slug=ws.slug)

@router.get('', response_model=list[WorkspaceOut])
async def list_workspaces():
    with workspace_session('public') as s:
        rows = s.execute(select(Workspace)).scalars().all()
        return [WorkspaceOut(id=w.id, name=w.name, slug=w.slug) for w in rows]
