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
