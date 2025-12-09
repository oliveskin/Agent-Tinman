"""Database connection management."""

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from .models import Base


class Database:
    """Database connection manager."""

    def __init__(self, url: str, pool_size: int = 10):
        self.url = url
        self.engine = create_engine(
            url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=20,
            pool_pre_ping=True,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

    def create_tables(self) -> None:
        """Create all tables."""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self) -> None:
        """Drop all tables (use with caution)."""
        Base.metadata.drop_all(bind=self.engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around operations."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self) -> Session:
        """Get a new session (caller must manage lifecycle)."""
        return self.SessionLocal()


_db_instance: Optional[Database] = None


def init_db(url: str, pool_size: int = 10) -> Database:
    """Initialize the global database instance."""
    global _db_instance
    _db_instance = Database(url, pool_size)
    return _db_instance


def get_db() -> Database:
    """Get the global database instance."""
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db_instance


# Alias for backwards compatibility
DatabaseConnection = Database
