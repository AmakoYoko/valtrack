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
    url: Optional[str] = None

class IssueOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    status: str
    priority: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    status: Optional[str] = None       # 'open' | 'in_progress' | 'closed'
    priority: Optional[str] = None     # 'low' | 'normal' | 'high' | 'urgent'
class CommentCreate(BaseModel):
    issue_id: str
    body: str

class CommentOut(BaseModel):
    id: str
    issue_id: str
    body: str
    created_at: Optional[str] = None
