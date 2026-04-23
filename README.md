# HNG Internship 14 — Stage 2: Intelligence Query Engine

A FastAPI backend for Insighta Labs — supports filtering, sorting, pagination, and natural language search over 2026 demographic profiles.

**Live URL:** `https://hng-internship14-stage1-profile-production.up.railway.app`

---

## Endpoints

### `POST /api/profiles`
Create a profile.

```json
{ "name": "amara" }
```
Response `201`:
```json
{ "status": "success", "data": { ...profile } }
```

---

### `GET /api/profiles`
List profiles with filtering, sorting, pagination.

**Filters:**

| Param | Type | Description |
|---|---|---|
| `gender` | string | `male` or `female` |
| `age_group` | string | `child`, `teenager`, `adult`, `senior` |
| `country_id` | string | ISO 2-letter code e.g. `NG`, `KE` |
| `min_age` | int | Minimum age inclusive |
| `max_age` | int | Maximum age inclusive |
| `min_gender_probability` | float | Minimum gender confidence score |
| `min_country_probability` | float | Minimum country confidence score |
| `sort_by` | string | `age`, `created_at`, `gender_probability` |
| `order` | string | `asc` (default) or `desc` |
| `page` | int | Page number, default 1 |
| `limit` | int | Per page, default 10, max 50 |

**Response `200`:**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2026,
  "data": [ { ...profile }, ... ]
}
```

---

### `GET /api/profiles/search`
Natural language query search.

```
GET /api/profiles/search?q=young males from nigeria
```

**Response `200`:**
```json
{ "status": "success", "page": 1, "limit": 10, "total": 45, "data": [...] }
```

**Uninterpretable query:**
```json
{ "status": "error", "message": "Unable to interpret query" }
```

Supports `sort_by`, `order`, `page`, `limit` same as list endpoint.

---

## Natural Language Parsing

### Approach
Rule-based parsing only — no AI or LLMs. The query string is lowercased and matched using Python `re` (regex) patterns and exact string lookups against a country name dictionary.

### Supported Keywords and Mappings

| Query | Parsed As |
|---|---|
| `young males` | gender=male, min_age=16, max_age=24 |
| `females above 30` | gender=female, min_age=30 |
| `people from angola` | country_id=AO |
| `adult males from kenya` | gender=male, age_group=adult, country_id=KE |
| `male and female teenagers above 17` | age_group=teenager, min_age=17 |
| `senior females` | gender=female, age_group=senior |
| `children from ghana` | age_group=child, country_id=GH |
| `women below 30` | gender=female, max_age=30 |
| `men older than 40` | gender=male, min_age=40 |
| `teenagers between 15 and 18` | age_group=teenager, min_age=15, max_age=18 |

### How the Logic Works

1. **Gender:** Regex checks for `females?|women|woman|girls?` first, then `males?|men|man|boys?`. If both appear (e.g. "male and female"), no gender filter is applied.
2. **Age groups:** Exact keyword regex — `teenagers?`, `seniors?`, `children`, `adults?`. "young" maps to min_age=16, max_age=24 per spec (not a stored age_group).
3. **Age thresholds:** Regex captures `above/older than/over N` → min_age=N and `below/younger than/under N` → max_age=N. `between N and M` sets both bounds.
4. **Country:** Dictionary lookup of 50+ country names. Sorted longest-first to prevent "niger" matching before "nigeria".

### Limitations

- No synonym handling — "lads", "guys", "gentlemen" are not recognised as male.
- Only English-language queries are supported.
- Country matching requires the full name — "naija" or "naij" is not recognised as Nigeria.
- Ambiguous queries like "people" or "users" with no other keywords return `Unable to interpret query`.
- Age thresholds and age group keywords can conflict (e.g. "young adults above 30" — "young" sets max_age=24 but "above 30" sets min_age=30, producing an empty result set). No conflict resolution is attempted.
- Spelling errors are not corrected.

---

## Age Groups

| Label | Age Range |
|---|---|
| child | 0–12 |
| teenager | 13–19 |
| adult | 20–59 |
| senior | 60+ |

---

## Error Responses

All errors return:
```json
{ "status": "error", "message": "<description>" }
```

| Code | Meaning |
|---|---|
| 400 | Missing or empty parameter |
| 404 | Profile not found |
| 409 | Duplicate name on create |
| 422 | Invalid parameter type |
| 500 | Server error |

---

## Local Development

```bash
git clone https://github.com/Seek-Techs/hng-internship14-stage1-profile.git
cd hng-internship14-stage1-profile

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt

echo "DATABASE_URL=sqlite:///./profiles.db" > .env

# Seed the database
python seed.py --file profiles.json

# Start the server
uvicorn main:app --reload
```

Docs at `http://localhost:8000/docs`

---

## Seeding on Railway

See **Seeding on Railway** section below. Run once after deploy:

```bash
railway run python seed.py --file profiles.json
```
