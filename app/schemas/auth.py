from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    phone: str
    password: str
    second_password: str | None = None


class OTPVerifyRequest(BaseModel):
    challenge_id: str
    access_token: str


class MillerRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=10, max_length=20)
    business_name: str = Field(min_length=1, max_length=200)
    password: str
    second_password: str | None = None


class CommissiondarRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=10, max_length=20)
    password: str
    second_password: str | None = None
