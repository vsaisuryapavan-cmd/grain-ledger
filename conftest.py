import models

from database import Base, get_db
from test_database import test_engine, get_test_db

from main import app

# Create tables in the local test database
Base.metadata.create_all(bind=test_engine)

# Make FastAPI use the local test database
app.dependency_overrides[get_db] = get_test_db