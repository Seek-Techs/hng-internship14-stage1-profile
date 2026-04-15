from pydantic import BaseModel
from typing import Optional

class ProfileCreate(BaseModel):
    """This is what the user sends to us"""
    name: str

class ProfileResponse(BaseModel):
    """This is what we return to the user"""
    id: str
    name: str
    gender: str
    gender_probability: float
    sample_size: int
    age: int
    age_group: str
    country_id: str
    country_probability: float
    created_at: str

class ErrorResponse(BaseModel):
    """Standard error format"""
    status: str = "error"
    message: str