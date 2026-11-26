import app.models  # noqa: F401

from app.core.database import Base, get_db
from app.main import app
from tests.test_database import get_test_db, test_engine

# Create tables in the local test database
Base.metadata.create_all(bind=test_engine)

# Make FastAPI use the local test database
app.dependency_overrides[get_db] = get_test_db
