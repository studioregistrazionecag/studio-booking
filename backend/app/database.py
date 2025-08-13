from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
import os

from .config import settings

APP_ENV = os.getenv("APP_ENV", "dev").lower()  # "dev" | "prod"

def _make_engine():
    # In sviluppo: nessun pool -> connessione chiusa subito dopo ogni request
    if APP_ENV != "prod":
        return create_engine(
            settings.DB_URL,
            future=True,
            pool_pre_ping=True,
            poolclass=NullPool,
        )

    # In produzione (Render): pool minimo e prudente
    return create_engine(
        settings.DB_URL,
        future=True,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        pool_recycle=1800,
    )

engine = _make_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # importantissimo per rilasciare la connessione