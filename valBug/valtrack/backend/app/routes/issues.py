# backend/app/routes/issues.py
from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select
from ..db import workspace_session
from ..schemas import IssueCreate, IssueOut, IssueUpdate, CommentCreate, CommentOut
from ..models_ws import Issue, Comment
from ..utils import ensure_workspace_schema  # ⬅️ ajoute ça

router = APIRouter(prefix="/issues", tags=["issues"])

def _schema_from_headers(x_workspace: str | None, x_workspace_id: str | None) -> str:
    if not x_workspace and not x_workspace_id:
        raise HTTPException(status_code=400, detail="X-Workspace or X-Workspace-ID required")
    if x_workspace:
        from ..utils import schema_name_from_slug
        return schema_name_from_slug(x_workspace)
    return f"ws_{x_workspace_id}"

@router.post('', response_model=IssueOut)
async def create_issue(body: IssueCreate, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    # 1) provision via public
    with workspace_session('public') as s:
        ensure_workspace_schema(s, schema)
    # 2) op métier dans le schéma
    with workspace_session(schema) as s:
        issue = Issue(title=body.title, description=body.description, url=body.url, priority=body.priority)
        s.add(issue)
        s.flush()
        return IssueOut(id=issue.id, title=issue.title, description=issue.description, url=issue.url, status=issue.status, priority=issue.priority, created_at=str(issue.created_at))

@router.get('', response_model=list[IssueOut])
async def list_issues(status: str | None = None, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session('public') as s:
        ensure_workspace_schema(s, schema)
    with workspace_session(schema) as s:
        q = select(Issue)
        if status:
            q = q.where(Issue.status == status)
        rows = s.execute(q).scalars().all()
        return [IssueOut(id=r.id, title=r.title, description=r.description, url=r.url, status=r.status, priority=r.priority, created_at=str(r.created_at), updated_at=str(r.updated_at) if r.updated_at else None) for r in rows]

@router.get('/{issue_id}', response_model=IssueOut)
async def get_issue(issue_id: str, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session('public') as s:
        ensure_workspace_schema(s, schema)
    with workspace_session(schema) as s:
        row = s.get(Issue, issue_id)
        if not row:
            raise HTTPException(status_code=404, detail="Issue not found")
        return IssueOut(id=row.id, title=row.title, description=row.description, url=row.url, status=row.status, priority=row.priority, created_at=str(row.created_at), updated_at=str(row.updated_at) if row.updated_at else None)

@router.post('/comments', response_model=CommentOut)
async def add_comment(body: CommentCreate, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session('public') as s:
        ensure_workspace_schema(s, schema)
    with workspace_session(schema) as s:
        c = Comment(issue_id=body.issue_id, body=body.body)
        s.add(c)
        s.flush()
        return CommentOut(id=c.id, issue_id=c.issue_id, body=c.body, created_at=str(c.created_at))
@router.get('/{issue_id}/comments', response_model=list[CommentOut])
async def list_comments(issue_id: str, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session('public') as s_pub:
        ensure_workspace_schema(s_pub, schema)
    with workspace_session(schema) as s:
        q = select(Comment).where(Comment.issue_id == issue_id)
        rows = s.execute(q).scalars().all()
        return [CommentOut(id=r.id, issue_id=r.issue_id, body=r.body, created_at=str(r.created_at)) for r in rows]

@router.patch('/{issue_id}', response_model=IssueOut)
async def update_issue(issue_id: str, body: IssueUpdate, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session('public') as s_pub:
        ensure_workspace_schema(s_pub, schema)
    with workspace_session(schema) as s:
        row = s.get(Issue, issue_id)
        if not row:
            raise HTTPException(status_code=404, detail="Issue not found")
        if body.title is not None: row.title = body.title
        if body.description is not None: row.description = body.description
        if body.url is not None: row.url = body.url
        if body.priority is not None: row.priority = body.priority
        if body.status is not None: row.status = body.status
        s.flush()
        return IssueOut(id=row.id, title=row.title, description=row.description, url=row.url, status=row.status, priority=row.priority, created_at=str(row.created_at), updated_at=str(row.updated_at) if row.updated_at else None)

@router.post('/{issue_id}/close', response_model=IssueOut)
async def close_issue(issue_id: str, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    return await update_issue(issue_id, IssueUpdate(status='closed'), X_Workspace, X_Workspace_ID)

@router.post('/{issue_id}/reopen', response_model=IssueOut)
async def reopen_issue(issue_id: str, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    return await update_issue(issue_id, IssueUpdate(status='open'), X_Workspace, X_Workspace_ID)

@router.delete('/{issue_id}')
async def delete_issue(issue_id: str, X_Workspace: str | None = Header(default=None), X_Workspace_ID: str | None = Header(default=None)):
    schema = _schema_from_headers(X_Workspace, X_Workspace_ID)
    with workspace_session('public') as s_pub:
        ensure_workspace_schema(s_pub, schema)
    with workspace_session(schema) as s:
        row = s.get(Issue, issue_id)
        if not row:
            raise HTTPException(status_code=404, detail="Issue not found")
        s.delete(row)
        s.flush()
        return {"ok": True}