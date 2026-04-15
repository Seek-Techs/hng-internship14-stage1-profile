# HNG Stage 1 — Profile Intelligence Service

A FastAPI service that accepts a name, enriches it using Genderize, Agify, and Nationalize APIs, persists the result, and exposes RESTful endpoints for retrieval and management.

## Tech Stack
- Python 3.10+
- FastAPI
- SQLAlchemy (SQLite)
- UUID v7 (`uuid6` package)
- httpx (async HTTP)

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 8000
```

## Base URL

```
https://your-deployed-app.domain
```

## Endpoints

### POST /api/profiles
Create a profile by name. Idempotent — returns existing record if name already exists.

**Request**
```json
{ "name": "ella" }
```

**Response 201**
```json
{
  "status": "success",
  "data": {
    "id": "uuid-v7",
    "name": "ella",
    "gender": "female",
    "gender_probability": 0.99,
    "sample_size": 1234,
    "age": 46,
    "age_group": "adult",
    "country_id": "DRC",
    "country_probability": 0.85,
    "created_at": "2026-04-01T12:00:00Z"
  }
}
```

---

### GET /api/profiles/{id}
Fetch a single profile by UUID.

---

### GET /api/profiles
List all profiles. Supports optional case-insensitive query filters:
- `gender`
- `country_id`
- `age_group`

Example: `/api/profiles?gender=male&country_id=NG`

---

### DELETE /api/profiles/{id}
Delete a profile. Returns `204 No Content`.

---

## Error Responses

All errors follow:
```json
{ "status": "error", "message": "<description>" }
```

| Code | Meaning |
|------|---------|
| 400  | Missing or empty name |
| 422  | Invalid type (e.g. name is not a string) |
| 404  | Profile not found |
| 502  | External API returned invalid/null data |
