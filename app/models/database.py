from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config import settings
from app.models.scan import Base
import logging

logger = logging.getLogger(__name__)

# Use SQLite for dev if PostgreSQL not available
try:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10
    )
    # Test connection
    with engine.connect() as conn:
        pass
    logger.info(f"Connected to PostgreSQL: {settings.DB_HOST}/{settings.DB_NAME}")
except Exception as e:
    logger.warning(f"PostgreSQL unavailable ({e}), falling back to SQLite")
    engine = create_engine(
        "sqlite:///./salesforce_dev.db",
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
