from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from app.core.config import get_settings

settings = get_settings()
# Force driver conversion to psycopg2 cleanly
SYNC_DATABASE_URL = settings.database_url.replace("postgresql://", "postgresql+psycopg2://")

engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_sync_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()