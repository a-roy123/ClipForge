import uuid
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str

    model_config = {"from_attributes": True}

class UserAuthResponse(BaseModel):
    access_token: str
    user: UserResponse

class UserLogin(BaseModel):
    email: EmailStr
    password: str