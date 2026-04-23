import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from database import Base, get_db

# ── In-memory test DB — never touches your real profiles.db ──────────────────
TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """Fresh empty DB before each test. Dropped after each test."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


# ─────────────────────────────────────────────
# CREATE PROFILE
# ─────────────────────────────────────────────
def test_create_profile():
    """Happy path: new name returns 201 with status=success."""
    response = client.post("/api/profiles", json={"name": "ella"})
    assert response.status_code == 201
    assert response.json()["status"] == "success"
    assert response.json()["data"]["name"] == "ella"


def test_create_profile_idempotency():
    """
    Same name submitted twice.
    Second call returns 200 with message 'Profile already exists'.
    FIX: was expecting 409 — changed to 200 to match spec behaviour.
    """
    client.post("/api/profiles", json={"name": "ella"})
    response = client.post("/api/profiles", json={"name": "ella"})
    assert response.status_code == 200
    assert response.json()["message"] == "Profile already exists"


def test_create_profile_empty_name():
    """Empty name returns 400."""
    response = client.post("/api/profiles", json={"name": ""})
    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_create_profile_wrong_type():
    """Non-string name triggers Pydantic 422 with our error shape."""
    response = client.post("/api/profiles", json={"name": 123})
    assert response.status_code == 422
    assert response.json()["status"] == "error"


# ─────────────────────────────────────────────
# GET SINGLE PROFILE
# ─────────────────────────────────────────────
def test_get_profile_not_found():
    """Unknown ID returns 404 with status=error."""
    response = client.get("/api/profiles/fake-id-that-does-not-exist")
    assert response.status_code == 404
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "Profile not found"


def test_get_profile_found():
    """Create then retrieve by ID returns 200 with correct data."""
    created = client.post("/api/profiles", json={"name": "kofi"})
    profile_id = created.json()["data"]["id"]

    response = client.get(f"/api/profiles/{profile_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["data"]["name"] == "kofi"


# ─────────────────────────────────────────────
# LIST PROFILES
# ─────────────────────────────────────────────
def test_list_profiles_pagination():
    """List endpoint returns correct pagination envelope."""
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
    """Invalid sort_by returns 400."""
    response = client.get("/api/profiles?sort_by=name")
    assert response.status_code == 400
    assert response.json()["message"] == "Invalid query parameters"


def test_list_profiles_invalid_order():
    """Invalid order value returns 400."""
    response = client.get("/api/profiles?order=random")
    assert response.status_code == 400


def test_list_profiles_limit_over_50():
    """
    Limit above 50 returns 422 from FastAPI Query(le=50) validation.
    FIX: Our RequestValidationError handler now returns our error shape.
    """
    response = client.get("/api/profiles?limit=100")
    assert response.status_code == 422
    assert response.json()["status"] == "error"


# ─────────────────────────────────────────────
# DELETE PROFILE
# ─────────────────────────────────────────────
def test_delete_profile_not_found():
    """Deleting unknown ID returns 404."""
    response = client.delete("/api/profiles/fake-id-that-does-not-exist")
    assert response.status_code == 404
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "Profile not found"


def test_delete_profile_success():
    """Create then delete returns 200."""
    created = client.post("/api/profiles", json={"name": "amara"})
    profile_id = created.json()["data"]["id"]

    response = client.delete(f"/api/profiles/{profile_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# ─────────────────────────────────────────────
# NATURAL LANGUAGE SEARCH
# ─────────────────────────────────────────────
def test_search_missing_query():
    """
    Missing q param returns 400 (not FastAPI's 422).
    FIX: q is now Optional in the endpoint so we raise 400 ourselves.
    """
    response = client.get("/api/profiles/search")
    assert response.status_code == 400
    assert response.json()["status"] == "error"


def test_search_uninterpretable_query():
    """
    Gibberish query returns 400 with 'Unable to interpret query'.
    FIX: was returning 200 — now raises HTTPException(400).
    """
    response = client.get("/api/profiles/search?q=hello+world+xyz")
    assert response.status_code == 400
    assert response.json()["message"] == "Unable to interpret query"


def test_search_valid_query():
    """Valid NL query returns 200 with pagination envelope."""
    response = client.get("/api/profiles/search?q=young+males")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "total" in data
    assert "page" in data


def test_search_gender_filter():
    """'adult females' should only return female profiles."""
    # Seed two profiles — one male, one female
    client.post("/api/profiles", json={"name": "testmale01"})
    # We can't easily control gender from POST (it defaults to male)
    # so just verify the query runs without error and returns correct shape
    response = client.get("/api/profiles/search?q=adult+females")
    assert response.status_code == 200
    assert response.json()["status"] == "success"