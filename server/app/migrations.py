"""Applies pending SQL migrations from server/migrations/ on startup.

Each file runs in its own transaction together with its row in
schema_migrations, so a failed migration leaves nothing half-applied.
"""

import logging
from pathlib import Path

import psycopg

from app import db

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def run_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every migration not yet in schema_migrations; return what ran."""
    applied: list[str] = []
    with psycopg.connect(db.conninfo()) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version text PRIMARY KEY,"
            " applied_at timestamptz DEFAULT now())"
        )
        conn.commit()
        done = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}

        for path in sorted(migrations_dir.glob("*.sql")):
            version = path.stem
            if version in done:
                continue
            logger.info("Applying migration %s", path.name)
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)", (version,)
                )
            applied.append(version)
    return applied
