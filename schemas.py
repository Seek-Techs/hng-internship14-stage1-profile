from pydantic import BaseModel


class ProfileCreate(BaseModel):
    name: str


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str
