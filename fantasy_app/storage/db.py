import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fantasy_app.storage.models import Base

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")

_engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    return SessionLocal()
