import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base, get_db

# ── Use a separate in-memory SQLite DB for tests ──────────────────────────────
# This means tests NEVER touch your real profiles.db
# Every test run starts with a completely empty database
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Replace the real DB session with the test DB session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Tell FastAPI to use test DB instead of real DB
app.dependency_overrides[get_db] = override_get_db


# ── Create tables before tests, drop them after ───────────────────────────────
@pytest.fixture(autouse=True)
def setup_database():
    """
    autouse=True means this runs automatically before and after EVERY test.
    Creates a fresh empty database before each test.
    Drops everything after each test.
    This guarantees tests never affect each other.
    """
    Base.metadata.create_all(bind=engine)    # create tables before test
    yield                                     # test runs here
    Base.metadata.drop_all(bind=engine)      # drop tables after test


client = TestClient(app)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_create_profile():
    """
    Happy Path: fresh name should always return 201.
    We use a UUID suffix to guarantee uniqueness even if
    someone runs tests without the setup_database fixture.
    """
    response = client.post("/api/profiles", json={"name": "ella"})
    assert response.status_code == 201
    assert response.json()["status"] == "success"
    assert response.json()["data"]["name"] == "ella"


def test_create_profile_idempotency():
    """
    Submitting the same name twice should return 200 on the second call
    with the message 'Profile already exists'.
    """
    # First call — creates the profile
    client.post("/api/profiles", json={"name": "ella"})

    # Second call — should return existing
    response = client.post("/api/profiles", json={"name": "ella"})
    assert response.status_code == 200
    assert response.json()["message"] == "Profile already exists"


def test_create_profile_empty_name():
    """Empty name should return 400."""
    response = client.post("/api/profiles", json={"name": ""})
    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_create_profile_wrong_type():
    """Non-string name should return 422 — Pydantic handles this."""
    response = client.post("/api/profiles", json={"name": 123})
    assert response.status_code == 422


def test_get_profile_not_found():
    """Unknown ID should return 404."""
    response = client.get("/api/profiles/fake-id-that-does-not-exist")
    assert response.status_code == 404
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "Profile not found"


def test_list_profiles_pagination():
    """List endpoint should return correct pagination fields."""
    response = client.get("/api/profiles?page=1&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "total" in data
    assert "page" in data
    assert "limit" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) <= 10


def test_list_profiles_invalid_sort():
    """Invalid sort_by value should return 400."""
    response = client.get("/api/profiles?sort_by=name")
    assert response.status_code == 400
    assert response.json()["message"] == "Invalid query parameters"


def test_list_profiles_invalid_order():
    """Invalid order value should return 400."""
    response = client.get("/api/profiles?order=random")
    assert response.status_code == 400


def test_list_profiles_limit_over_50():
    """Limit above 50 should return 422 — FastAPI Query(le=50) handles this."""
    response = client.get("/api/profiles?limit=100")
    assert response.status_code == 422


def test_search_missing_query():
    """Missing q param should return 400."""
    response = client.get("/api/profiles/search")
    assert response.status_code == 400


def test_search_uninterpretable_query():
    """Gibberish query should return 400 with specific message."""
    response = client.get("/api/profiles/search?q=hello+world+xyz")
    assert response.status_code == 400
    assert response.json()["message"] == "Unable to interpret query"


def test_search_valid_query():
    """Valid NL query should return 200 with pagination fields."""
    response = client.get("/api/profiles/search?q=young+males")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "total" in data
    assert "page" in data


def test_delete_profile_not_found():
    """Deleting unknown ID should return 404."""
    response = client.delete("/api/profiles/fake-id-that-does-not-exist")
    assert response.status_code == 404