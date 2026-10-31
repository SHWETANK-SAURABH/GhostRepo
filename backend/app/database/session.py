"""Engine and session lifecycle. The schema is created on startup with create_all."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.database.models import Base


class Database:
    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite" and parsed.database:
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 30}
        )
        event.listen(self.engine, "connect", _configure_sqlite)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def init_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self._sessions()

    @contextmanager
    def scope(self) -> Iterator[Session]:
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


def _configure_sqlite(connection, _record) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.database.session()
    try:
        yield session
    finally:
        session.close()
