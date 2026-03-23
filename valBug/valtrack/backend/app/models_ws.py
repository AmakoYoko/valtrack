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
    url = Column(String, nullable=True)
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
