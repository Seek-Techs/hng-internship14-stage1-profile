import os
from sqlalchemy import Index, create_engine, Column, String, Float, Integer, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
from uuid6 import uuid7
from dotenv import load_dotenv
import sys 

load_dotenv()  # loads .env file in local dev; on cloud, env vars are injected directly

# validate environment variables before the app starts:
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./profiles.db")
if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable is not set")
    sys.exit(1)

# Heroku and some other platforms still supply the old postgres:// scheme
# SQLAlchemy 1.4+ requires postgresql:// — fix it silently
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite needs check_same_thread=False for FastAPI's threading model
# PostgreSQL does not need (or accept) this argument
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_size=5,        # maintain 5 persistent connections
        max_overflow=10,    # allow 10 extra connections under load
        pool_timeout=30,    # wait max 30s for a connection
        pool_pre_ping=True, # test connection health before using it
    )
else:
    engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20, pool_timeout=30, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = Column(String, primary_key=True, default=lambda: str(uuid7()), index=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    name = Column(String, unique=True, index=True, nullable=False)

    # ── Gender fields ─────────────────────────────────────────────────────────
    gender = Column(String, nullable=False)


    gender_probability = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=False)

    # ── Age fields ─────────────────────────────────────────────────────────────
    age = Column(Integer, nullable=False)
    age_group = Column(String, nullable=False)

    # ── Location fields ───────────────────────────────────────────────────────
    # country_id   → 2-letter ISO code  e.g. "NG"
    # country_name → full name          e.g. "Nigeria" 
    country_id = Column(String(2), nullable=False)
    country_name = Column(String, nullable=False)
    country_probability = Column(Float, nullable=False)

    # ── Metadata ──────────────────────────────────────────────────────────────

    # UTC default — explicit lambda so it works the same on SQLite and PostgreSQL
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    # Defined here using __table_args__ so SQLAlchemy creates them automatically
    # alongside the table. Each index speeds up one category of filter/sort.
    __table_args__ = (
        # Single-column indexes — for individual filter queries
        Index("ix_profiles_gender", "gender"),
        Index("ix_profiles_country_id", "country_id"),
        Index("ix_profiles_age_group", "age_group"),
        Index("ix_profiles_age", "age"),
        Index("ix_profiles_gender_probability", "gender_probability"),
        Index("ix_profiles_country_probability", "country_probability"),
        Index("ix_profiles_created_at", "created_at"),
 
        # Composite index — speeds up the most common combined query:
        # filtering by gender + country_id together (e.g. "male from NG")
        Index("ix_profiles_gender_country", "gender", "country_id"),
    )

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
