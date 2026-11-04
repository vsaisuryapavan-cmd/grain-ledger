
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base

# Load the separate testing environment
load_dotenv(".env.test", override=True)

TEST_DATABASE_URL = os.getenv("DATABASE_URL")

if not TEST_DATABASE_URL:
    raise RuntimeError("DATABASE_URL missing from .env.test")

if TEST_DATABASE_URL.startswith("postgresql://"):
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg2://",
        1
    )

test_engine = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True
)

TestSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)


def get_test_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
