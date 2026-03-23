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
