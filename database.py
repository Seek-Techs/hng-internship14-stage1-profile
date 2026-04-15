from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
import uuid
from uuid6 import uuid7   # This gives us real UUID v7

DATABASE_URL = "sqlite:///./profiles.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Create tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()