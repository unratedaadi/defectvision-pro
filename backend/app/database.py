from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import Settings, ROOT


class Base(DeclarativeBase):
    pass


def database_engine(settings: Settings):
    path = ROOT / settings.database_path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create("sqlite", database=str(path)))

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")

    return engine


def session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine, expire_on_commit=False) as db:
        yield db


DB = Annotated[Session, Depends(session)]
