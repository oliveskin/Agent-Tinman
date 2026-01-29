"""Database connection management."""

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine.url import make_url
import os

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

    def disconnect(self) -> None:
        """Dispose the engine and close all pooled connections."""
        if self.engine:
            self.engine.dispose()


def ensure_database(url: str) -> dict:
    """Ensure the target database exists and tables are created."""
    parsed = make_url(url)
    backend = parsed.get_backend_name()

    if backend.startswith("sqlite"):
        db = Database(url)
        db.create_tables()
        return {"backend": "sqlite", "database": parsed.database or url, "created": True}

    if backend.startswith("postgres"):
        db_name = parsed.database
        if not db_name:
            raise RuntimeError("Postgres URL must include a database name.")
        admin_db = os.environ.get("TINMAN_PG_ADMIN_DB", "postgres")
        admin_url = parsed.set(database=admin_db)

        engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        created = False
        with engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()
            if not exists:
                conn.exec_driver_sql(f'CREATE DATABASE "{db_name}"')
                created = True
        engine.dispose()

        db = Database(url)
        db.create_tables()
        return {"backend": "postgresql", "database": db_name, "created": created}

    raise RuntimeError(f"Unsupported database backend: {backend}")


def check_database(url: str) -> dict:
    """Check database connectivity and list tables."""
    engine = create_engine(url)
    try:
        with engine.connect():
            pass
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        return {"connected": True, "tables": tables}
    finally:
        engine.dispose()


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
