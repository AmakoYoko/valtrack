from sqlalchemy import text
from .models_ws import WSBase

WS_PREFIX = 'ws_'

def schema_name_from_slug(slug: str) -> str:
    s = slug.lower().replace(' ', '-')
    safe = ''.join(c for c in s if c.isalnum() or c in ('-', '_'))
    safe = safe.replace('-', '_')
    return WS_PREFIX + safe

def ensure_workspace_schema(session, schema: str):
    # 1) Schéma
    session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    # 2) Se placer dessus
    session.execute(text("SET search_path TO :sp"), {"sp": schema})
    # 3) Créer via ORM
    WSBase.metadata.create_all(bind=session.get_bind(), checkfirst=True)
    # 4) Sanity check + DDL fallback (au cas où la détection ORM rate)
    ok = session.execute(
        text("SELECT to_regclass(:t) IS NOT NULL"),
        {"t": f"{schema}.issues"}
    ).scalar()
    if not ok:
        session.execute(text(f'''
        CREATE TABLE IF NOT EXISTS "{schema}".issues (
          id text PRIMARY KEY,
          title varchar NOT NULL,
          description text,
          url varchar,
          status varchar DEFAULT 'open',
          priority varchar DEFAULT 'normal',
          reporter_id text,
          assignee_id text,
          created_at timestamptz DEFAULT now(),
          updated_at timestamptz
        );
        CREATE TABLE IF NOT EXISTS "{schema}".comments (
          id text PRIMARY KEY,
          issue_id text REFERENCES "{schema}".issues(id) ON DELETE CASCADE,
          author_id text,
          body text NOT NULL,
          created_at timestamptz DEFAULT now()
        );
        '''))
    session.execute(text(f'ALTER TABLE "{schema}".issues ADD COLUMN IF NOT EXISTS url varchar'))