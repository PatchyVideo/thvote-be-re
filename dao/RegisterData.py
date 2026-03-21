from pydantic import BaseModel


class RegisterData(BaseModel):
    username: str
    password: str
    phone_number: str
    email: str
