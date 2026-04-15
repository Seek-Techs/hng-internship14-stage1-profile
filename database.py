import os
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone
from uuid6 import uuid7
from dotenv import load_dotenv

load_dotenv()  # loads .env file in local dev; on cloud, env vars are injected directly

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./profiles.db")

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
    )
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid7()), index=True)
    name = Column(String, unique=True, index=True, nullable=False)

    gender = Column(String, nullable=False)
    gender_probability = Column(Float, nullable=False)
    sample_size = Column(Integer, nullable=False)

    age = Column(Integer, nullable=False)
    age_group = Column(String, nullable=False)

    country_id = Column(String, nullable=False)
    country_probability = Column(Float, nullable=False)

    # UTC default — explicit lambda so it works the same on SQLite and PostgreSQL
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
