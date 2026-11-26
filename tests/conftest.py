import app.models  # noqa: F401
import app.core.security as _security_module
import pytest

from app.core.database import Base, get_db
from app.main import app
from tests.test_database import get_test_db, test_engine

# Create tables in the local test database
Base.metadata.create_all(bind=test_engine)

# Make FastAPI use the local test database
app.dependency_overrides[get_db] = get_test_db

@pytest.fixture(autouse=True)
def mock_msg91_verification(monkeypatch):
    monkeypatch.setattr(
        _security_module,
        "verify_msg91_access_token",
        lambda access_token: access_token.split(":", 1)[1]
    )
