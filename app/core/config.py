import os
from dotenv import load_dotenv

load_dotenv()

if os.getenv("APP_ENV") != "production":
    load_dotenv(".env.test", override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg2://",
        1,
    )

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not configured")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

MSG91_AUTHKEY = os.getenv("MSG91_AUTHKEY")
APP_ENV = os.getenv("APP_ENV", "production")
OTP_DELIVERY_MODE = os.getenv("OTP_DELIVERY_MODE", "disabled")

_default_cors = [
    "http://localhost:5173",
    "https://rice-mill-ledger.onrender.com",
]
_env_cors = os.getenv("CORS_ORIGINS")
CORS_ORIGINS = (
    [origin.strip() for origin in _env_cors.split(",") if origin.strip()]
    if _env_cors
    else _default_cors
)
