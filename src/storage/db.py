"""Phase 3 — Database engine & session setup.

Turns the schema in schema.py into a real database file on disk
(db/finance.db by default) and gives the rest of the app a way to talk
to it. Nothing in schema.py touches the filesystem — this file is what
does.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.storage.schema import Base

load_dotenv()  # reads .env if present; falls back to the default below if not

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db/finance.db")

# echo=False keeps raw SQL out of stdout by default. Flip to True
# temporarily if you ever want to see exactly what SQL SQLAlchemy is
# generating for a query — genuinely useful for learning/debugging.
engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables from schema.py if they don't already exist.

    Idempotent — safe to call every time the app starts. It only adds
    missing tables, it never drops or overwrites existing data.
    """
    Path("db").mkdir(exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    """Open a new database session.

    Use as a context manager so it always closes:
        with get_session() as session:
            session.add(some_object)
            session.commit()
    """
    return SessionLocal()


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at: {DATABASE_URL}")