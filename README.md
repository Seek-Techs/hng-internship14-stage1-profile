# HNG Stage 2 — Profiles API

A FastAPI + PostgreSQL REST API that stores and queries people profiles enriched with gender, age, and nationality predictions.

Live URL: `https://hng-internship14-stage1-profile-production.up.railway.app`

---

## Tech Stack

- **FastAPI** — web framework
- **SQLAlchemy** — ORM + query layer
- **PostgreSQL** — production database (Railway)
- **psycopg2** — PostgreSQL driver
- **uuid6 / uuid7** — time-ordered unique IDs
- **uvicorn** — ASGI server

---

## Local Setup

```bash
git clone https://github.com/Seek-Techs/hng-internship14-stage1-profile.git
cd hng-internship14-stage1-profile

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Create a .env file with your database connection
echo "DATABASE_URL=postgresql://user:pass@localhost:5432/profiles" > .env

# Start the server
uvicorn main:app --reload
```

Seed the database (optional):
```bash
python seed.py --file profiles.json
```

---

## API Endpoints

### POST `/api/profiles`
Create a new profile by name.

**Request body:**
```json
{ "name": "john doe" }
```

**Response (201):**
```json
{
  "status": "success",
  "data": { "id": "...", "name": "john doe", "gender": "male", ... }
}
```

---

### GET `/api/profiles`
List all profiles with optional filtering, sorting, and pagination.

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `gender` | string | `male` or `female` |
| `age_group` | string | `child`, `teenager`, `adult`, `senior` |
| `country_id` | string | ISO 2-letter code e.g. `NG` |
| `min_age` | int | Minimum age (inclusive) |
| `max_age` | int | Maximum age (inclusive) |
| `min_gender_probability` | float | e.g. `0.8` |
| `min_country_probability` | float | e.g. `0.7` |
| `sort_by` | string | `age`, `created_at`, or `gender_probability` |
| `order` | string | `asc` (default) or `desc` |
| `page` | int | Page number (default: 1) |
| `limit` | int | Results per page (default: 10, max: 50) |

**Response (200):**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 243,
  "data": [ ... ]
}
```

---

### GET `/api/profiles/search`
Natural language query search.

**Query parameters:**

| Parameter | Description |
|---|---|
| `q` | Natural language query string (required) |
| `sort_by`, `order`, `page`, `limit` | Same as list endpoint |

**Supported query patterns:**

| Query | Interpretation |
|---|---|
| `young males` | gender=male, age 16–24 |
| `females above 30` | gender=female, min_age=30 |
| `people from nigeria` | country_id=NG |
| `adult males from kenya` | gender=male, age_group=adult, country_id=KE |
| `Male and female teenagers above 17` | age_group=teenager, min_age=17 |
| `seniors from ghana` | age_group=senior, country_id=GH |

**Response (200):**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 18,
  "data": [ ... ]
}
```

**Error (400) — uninterpretable query:**
```json
{ "status": "error", "message": "Unable to interpret query" }
```

---

### GET `/api/profiles/{profile_id}`
Fetch a single profile by ID.

**Response (200):**
```json
{ "status": "success", "data": { ... } }
```

**Error (404):**
```json
{ "status": "error", "message": "Profile not found" }
```

---

### DELETE `/api/profiles/{profile_id}`
Delete a profile by ID.

**Response (200):**
```json
{ "status": "success", "message": "Profile deleted" }
```

---

## Natural Language Parsing Logic

The `/api/profiles/search` endpoint uses a **rule-based parser** (no LLMs). It extracts filters by matching regex patterns against the query string:

- **Gender** — detects `male/men/man/boys` and `female/women/woman/girls`; if both appear, no gender filter is applied
- **Age group** — keywords: `seniors/elderly`, `teenagers/teens`, `children/kids`, `young` (→ age 16–24), `adults`
- **Age thresholds** — phrases like `above 30`, `below 25`, `between 18 and 40`, `older than 50`
- **Country** — matches full country names (e.g. `nigeria`, `south africa`) and maps them to ISO codes

---

## Error Response Shape

All errors — including 404, 400, 422, and 500 — return:
```json
{ "status": "error", "message": "..." }
```

---

## Deployment

Deployed on **Railway** with a managed PostgreSQL database. Environment variable `DATABASE_URL` is injected automatically via Railway's Postgres plugin reference.
