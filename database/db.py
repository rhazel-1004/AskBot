"""
Database configuration and session management for AskBot.
Handles SQLAlchemy setup and database connections.
"""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Default to a local SQLite file when DATABASE_URL is unset — keeps local dev
# zero-config. Production sets DATABASE_URL to a PostgreSQL DSN (e.g. Render).
DEFAULT_SQLITE_URL = "sqlite:///./ask_bot.db"


def get_database_url() -> str:
    """Resolve the active database URL.

    - DATABASE_URL unset      → local SQLite file (dev default).
    - DATABASE_URL set        → used as-is (PostgreSQL in production).

    Render (and some other hosts) hand out URLs with the legacy ``postgres://``
    scheme, which SQLAlchemy 2.x no longer recognizes — normalize it to the
    ``postgresql://`` form psycopg2 expects so the same value works everywhere.
    """
    url = os.getenv("DATABASE_URL", "").strip() or DEFAULT_SQLITE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


# Resolve once at import time (the engine is a process-wide singleton).
DATABASE_URL = get_database_url()
_IS_SQLITE = is_sqlite_url(DATABASE_URL)

# Engine options differ per backend:
#   - SQLite needs check_same_thread=False (we share the connection across the
#     asyncio event loop + worker threads) and does NOT support real pooling.
#   - PostgreSQL benefits from connection recycling so Render's idle-connection
#     reaping doesn't hand us a dead socket.
_engine_kwargs = {
    "echo": False,  # Set to True for SQL logging in development
    "pool_pre_ping": True,  # Check connection health before using a pooled conn
}
if _IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # Recycle connections every 5 minutes; harmless ceiling on connection age.
    _engine_kwargs["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, **_engine_kwargs)

logger.info(
    "Database engine initialized (backend=%s)",
    "sqlite" if _IS_SQLITE else engine.dialect.name,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def init_db() -> None:
    """Initialize database tables."""
    from .models import User
    from .models_subscription import Subscription, Payment
    from .models_webhook import WebhookProcessingLog  # noqa: F401
    from .models_checkout import CheckoutSession  # noqa: F401
    from .models_question_draft import QuestionSubmissionDraft  # noqa: F401
    from .models_email_idempotency import EmailNotificationLog  # noqa: F401
    from .models_app_setting import AppSetting  # noqa: F401
    from .migration_runner import run_baseline_migrations
    
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        run_baseline_migrations(engine)
        logger = logging.getLogger(__name__)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating database tables: {e}")


def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
