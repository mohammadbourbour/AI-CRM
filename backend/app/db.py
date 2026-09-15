from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.models import Base

_engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None


def _sqlite_kwargs(url: str) -> dict:
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in url or url.endswith("sqlite://"):
        kwargs["poolclass"] = StaticPool
    return kwargs


def configure_engine(database_url: str | None = None) -> Engine:
    global _engine, SessionLocal
    url = database_url or get_settings().database_url
    if url.startswith("sqlite") and ":memory:" not in url:
        db_path = url.split("sqlite:///")[-1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    extra = _sqlite_kwargs(url) if url.startswith("sqlite") else {}
    _engine = create_engine(url, **extra)
    SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return configure_engine()
    return _engine


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        configure_engine()
    assert SessionLocal is not None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
