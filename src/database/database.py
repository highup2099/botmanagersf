"""
Database initialization and session management.
Uses SQLAlchemy for ORM with SQLite backend.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from src.config.settings import settings


# Base class for all models
Base = declarative_base()


def get_engine():
    """Create and return database engine."""
    return create_engine(
        settings.DATABASE_URL,
        echo=settings.APP_ENV == "development",
        connect_args={"check_same_thread": False}  # Needed for SQLite
    )


def get_session_factory(engine=None):
    """Create session factory."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_database():
    """Initialize database by creating all tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    return engine


def get_db_session() -> Session:
    """Get a database session. Use as context manager."""
    engine = get_engine()
    SessionLocal = get_session_factory(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class DatabaseManager:
    """Context manager for database sessions."""
    
    def __init__(self):
        self.engine = None
        self.session = None
    
    def __enter__(self) -> Session:
        self.engine = get_engine()
        SessionLocal = get_session_factory(self.engine)
        self.session = SessionLocal()
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()
