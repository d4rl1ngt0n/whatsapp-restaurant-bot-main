import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data.db")

engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):  # pragma: no cover
	engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, echo=False, future=True, **engine_kwargs)
SessionLocal = sessionmaker(
	bind=engine,
	autoflush=False,
	autocommit=False,
	future=True,
	expire_on_commit=False,
)

Base = declarative_base()


@contextmanager
def get_session() -> Iterator[SessionLocal]:  # type: ignore[name-defined]
	session = SessionLocal()
	try:
		yield session
		session.commit()
	except Exception:
		session.rollback()
		raise
	finally:
		session.close()


def init_db() -> None:
	from app import models  # noqa: F401
	try:
		Base.metadata.create_all(bind=engine)
	except OperationalError:
		pass
