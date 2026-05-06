from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(String, unique=True)
    username = Column(String)
    role = Column(String, default="analyst")
    oauth_state = Column(String, nullable=True)