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
