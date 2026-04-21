# Profile Intelligence Service — Stage 2

A FastAPI service that accepts names, enriches them using Genderize, Agify, and Nationalize APIs, persists the result, and exposes RESTful endpoints with advanced filtering, sorting, pagination, and natural language search.

---

## Tech Stack

- Python 3.10+
- FastAPI
- SQLAlchemy (PostgreSQL on Railway, SQLite for local dev)
- UUID v7 (`uuid6` package)
- httpx (async HTTP)
- python-dotenv

---

## Setup — Local Development

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```dotenv
DATABASE_URL=sqlite:///./profiles.db
```

Run the server:

```bash
venv\Scripts\uvicorn.exe main:app --reload --host 0.0.0.0 --port 8000
```

Seed the database:

```bash
python seed.py profiles.json
```

---

## Setup — Production (Railway)

1. Push repo to GitHub (must be public)
2. Create new Railway project → Deploy from GitHub repo
3. Add PostgreSQL plugin — Railway auto-injects `DATABASE_URL`
4. Link `DATABASE_URL` from Postgres service to app service via Variables tab
5. Railway reads `railway.toml` and starts with:
   ```
   uvicorn main:app --host 0.0.0.0 --port $PORT
   ```
6. Run seed via Railway shell:
   ```bash
   python seed.py profiles.json
   ```

---

## Base URL

```
https://your-app-name.up.railway.app
```

---

## Endpoints

### POST /api/profiles
Create a profile by name. Calls Genderize, Agify, and Nationalize concurrently.
Idempotent — returns existing record if name already exists.

**Request**
```json
{ "name": "ella" }
```

**Response 201**
```json
{
  "status": "success",
  "data": {
    "id": "019526b2-3c4d-7e8f-9a0b-1c2d3e4f5a6b",
    "name": "ella",
    "gender": "female",
    "gender_probability": 0.98,
    "sample_size": 4567,
    "age": 35,
    "age_group": "adult",
    "country_id": "NG",
    "country_name": "Nigeria",
    "country_probability": 0.12,
    "created_at": "2026-04-20T10:00:00Z"
  }
}
```

**Idempotency — 200 if name already exists**
```json
{
  "status": "success",
  "message": "Profile already exists",
  "data": { "...existing profile..." }
}
```

---

### GET /api/profiles
List all profiles with optional filtering, sorting, and pagination.

**Query Parameters**

| Parameter | Type | Description | Example |
|---|---|---|---|
| `gender` | string | Filter by gender | `male` |
| `age_group` | string | Filter by age group | `adult` |
| `country_id` | string | Filter by ISO country code | `NG` |
| `min_age` | integer | Minimum age (inclusive) | `25` |
| `max_age` | integer | Maximum age (inclusive) | `40` |
| `min_gender_probability` | float | Minimum gender confidence | `0.90` |
| `min_country_probability` | float | Minimum country confidence | `0.80` |
| `sort_by` | string | Sort field: `age`, `created_at`, `gender_probability` | `age` |
| `order` | string | Sort direction: `asc`, `desc` (default: `asc`) | `desc` |
| `page` | integer | Page number, default `1` | `2` |
| `limit` | integer | Results per page, default `10`, max `50` | `20` |

All filters are combinable. Results match every condition passed.

**Example**
```
GET /api/profiles?gender=male&country_id=NG&min_age=25&sort_by=age&order=desc&page=1&limit=10
```

**Response 200**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 142,
  "data": [
    {
      "id": "019526b2-3c4d-7e8f-9a0b-1c2d3e4f5a6b",
      "name": "emmanuel",
      "gender": "male",
      "gender_probability": 0.99,
      "age": 34,
      "age_group": "adult",
      "country_id": "NG",
      "country_name": "Nigeria",
      "country_probability": 0.85,
      "created_at": "2026-04-01T12:00:00Z"
    }
  ]
}
```

---

### GET /api/profiles/search
Natural language query endpoint. Parses plain English into filters.

**Query Parameters**

| Parameter | Type | Description |
|---|---|---|
| `q` | string | Plain English query |
| `page` | integer | Page number, default `1` |
| `limit` | integer | Results per page, default `10`, max `50` |

**Example**
```
GET /api/profiles/search?q=young males from nigeria&page=1&limit=10
```

**Response 200**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 38,
  "data": [ { "...profile..." } ]
}
```

**Uninterpretable query — 400**
```json
{
  "status": "error",
  "message": "Unable to interpret query"
}
```

---

### GET /api/profiles/{id}
Fetch a single profile by UUID v7.

**Response 200** — full profile object  
**Response 404** — `{ "status": "error", "message": "Profile not found" }`

---

### DELETE /api/profiles/{id}
Delete a profile by UUID v7.

**Response 204** — No Content  
**Response 404** — `{ "status": "error", "message": "Profile not found" }`

---

## Natural Language Parsing — How It Works

The `/api/profiles/search` endpoint uses **rule-based keyword parsing only**.
No AI or LLMs are used at any point.

### How the parser works

The query string is lowercased and split into tokens (individual words).
The parser then scans those tokens for known keyword patterns in this order:

```
1. Gender keywords
2. Age group keywords
3. "young" keyword (special case)
4. Age range keywords (above/below/over/under + number)
5. Country keywords (from + country name)
```

Each matched keyword adds a filter to the result dict.
If nothing matches at all, the parser returns `None` and the endpoint responds with `"Unable to interpret query"`.

---

### Supported Keywords and Their Filter Mappings

#### Gender
| Keyword(s) | Maps to |
|---|---|
| `male`, `males`, `man`, `men` | `gender=male` |
| `female`, `females`, `woman`, `women` | `gender=female` |
| both male and female keywords together | no gender filter (both genders = no restriction) |

#### Age Group
| Keyword(s) | Maps to |
|---|---|
| `child`, `children` | `age_group=child` |
| `teenager`, `teenagers`, `teens` | `age_group=teenager` |
| `adult`, `adults` | `age_group=adult` |
| `senior`, `seniors`, `elderly` | `age_group=senior` |

#### Special: "young"
| Keyword | Maps to |
|---|---|
| `young` | `min_age=16`, `max_age=24` |

`young` is **not** a stored age group. It only maps to an age range at parse time.

#### Age Range
| Pattern | Maps to |
|---|---|
| `above N`, `over N`, `older N` | `min_age=N` |
| `below N`, `under N`, `younger N` | `max_age=N` |

N must be an integer immediately following the keyword.

#### Country
| Pattern | Maps to |
|---|---|
| `from <country name>` | `country_id=<ISO code>` |

Both single-word (`nigeria`) and two-word (`south africa`, `sierra leone`) country names are supported.
The parser checks two-word combinations before single-word to correctly handle compound names.

---

### Example Query Mappings

| Query | Extracted Filters |
|---|---|
| `young males` | `gender=male, min_age=16, max_age=24` |
| `females above 30` | `gender=female, min_age=30` |
| `people from angola` | `country_id=AO` |
| `adult males from kenya` | `gender=male, age_group=adult, country_id=KE` |
| `male and female teenagers above 17` | `age_group=teenager, min_age=17` |
| `senior women from nigeria` | `gender=female, age_group=senior, country_id=NG` |
| `young females from ghana` | `gender=female, min_age=16, max_age=24, country_id=GH` |
| `children from tanzania` | `age_group=child, country_id=TZ` |

---

### Limitations and Known Edge Cases

**1. No numeric age without a keyword**
The query `"30 year olds"` is not supported. Age extraction requires a preceding keyword
like `above`, `below`, `over`, or `under`. Without it, the number is ignored.

**2. No compound gender + age group combinations without explicit keywords**
`"old men"` does not map to `senior + male`. Only explicit keywords like `"senior males"` work.
The word `"old"` alone is not a recognised keyword.

**3. Single country per query**
Only the first `"from <country>"` match is used. Queries like
`"males from nigeria or kenya"` will only extract `nigeria`.

**4. No negation support**
`"males not from nigeria"` will extract `gender=male` and `country_id=NG` — the word `"not"` is ignored.

**5. Country name must be in the lookup dictionary**
The parser covers ~60 countries. A country name absent from the dictionary
(e.g. a misspelling or an unlisted territory) will not be matched and `country_id` will not be set.

**6. "young" cannot combine with explicit age group keywords**
If a query contains both `"young"` and `"adult"`, `"adult"` takes precedence
because age group keywords are checked before the `"young"` special case.

**7. No fuzzy matching**
`"nigerian"` will not match `"nigeria"`. Keywords must match exactly after lowercasing.

**8. Ambiguous country names**
`"from guinea"` maps to Guinea (`GN`). Equatorial Guinea (`GQ`) requires the full name.
`"from congo"` maps to Republic of Congo (`CG`). DRC requires `"democratic republic of congo"` or `"drc"`.

---

## Error Reference

| Code | Meaning |
|---|---|
| 400 | Missing or empty parameter |
| 422 | Invalid parameter type (handled by Pydantic automatically) |
| 404 | Profile not found |
| 502 | External API (Genderize / Agify / Nationalize) returned invalid data |
| 500 | Unexpected server error |

All errors follow:
```json
{ "status": "error", "message": "<description>" }
```

---

## Running Tests

Tests use a separate isolated SQLite database — they never touch your real `profiles.db`.
Every test starts with a clean empty database and drops it after finishing.

### Install test dependency

```bash
pip install pytest
```

`pytest` is already listed in `requirements.txt` — this is only needed if you are setting up fresh.

### Run all tests

```bash
pytest test_main.py -v
```

### Run a single test

```bash
pytest test_main.py::test_create_profile -v
```

### Expected output

```
test_main.py::test_create_profile               PASSED
test_main.py::test_create_profile_idempotency   PASSED
test_main.py::test_create_profile_empty_name    PASSED
test_main.py::test_create_profile_wrong_type    PASSED
test_main.py::test_get_profile_not_found        PASSED
test_main.py::test_list_profiles_pagination     PASSED
test_main.py::test_list_profiles_invalid_sort   PASSED
test_main.py::test_list_profiles_invalid_order  PASSED
test_main.py::test_list_profiles_limit_over_50  PASSED
test_main.py::test_search_missing_query         PASSED
test_main.py::test_search_uninterpretable_query PASSED
test_main.py::test_search_valid_query           PASSED
test_main.py::test_delete_profile_not_found     PASSED
```

### What is tested

| Test | What it verifies |
|---|---|
| `test_create_profile` | Valid name returns 201 with correct shape |
| `test_create_profile_idempotency` | Same name twice returns 200 + "Profile already exists" |
| `test_create_profile_empty_name` | Empty name returns 400 |
| `test_create_profile_wrong_type` | Non-string name returns 422 |
| `test_get_profile_not_found` | Unknown ID returns 404 |
| `test_list_profiles_pagination` | Response has page, limit, total fields |
| `test_list_profiles_invalid_sort` | Invalid sort_by returns 400 |
| `test_list_profiles_invalid_order` | Invalid order returns 400 |
| `test_list_profiles_limit_over_50` | limit > 50 returns 422 |
| `test_search_missing_query` | Missing q param returns 400 |
| `test_search_uninterpretable_query` | Gibberish query returns 400 with correct message |
| `test_search_valid_query` | Valid NL query returns 200 with pagination fields |
| `test_delete_profile_not_found` | Deleting unknown ID returns 404 |


