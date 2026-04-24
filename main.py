from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc
from typing import Optional
import re
from database import Profile, get_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from database import init_db

@app.on_event("startup")
def on_startup():
    init_db()

# ─────────────────────────────────────────────
# GLOBAL ERROR HANDLERS
# All errors must return {"status": "error", "message": "..."}
# ─────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"},
    )

from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Invalid parameter type"},
    )


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────
class ProfileCreate(BaseModel):
    name: str


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_age_group(age: int) -> str:
    if age <= 12:
        return "child"
    elif age <= 19:
        return "teenager"
    elif age <= 59:
        return "adult"
    return "senior"


def serialize(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "gender": p.gender,
        "gender_probability": p.gender_probability,
        "age": p.age,
        "age_group": p.age_group,
        "country_id": p.country_id,
        "country_name": p.country_name,
        "country_probability": p.country_probability,
        "created_at": p.created_at.isoformat(),
    }


def paginate(query, page: int, limit: int) -> dict:
    limit = max(1, min(limit, 50))
    page  = max(1, page)
    total  = query.count()
    offset = (page - 1) * limit
    rows   = query.offset(offset).limit(limit).all()
    return {
        "status": "success",
        "page":   page,
        "limit":  limit,
        "total":  total,
        "data":   [serialize(r) for r in rows],
    }


# ─────────────────────────────────────────────
# COUNTRY NAME → ISO CODE MAP
# Keys sorted longest-first so "nigeria" never gets shadowed by "niger"
# ─────────────────────────────────────────────
COUNTRY_NAME_MAP = {
    "south africa":                 "ZA",
    "ivory coast":                  "CI",
    "cote d'ivoire":                "CI",
    "sierra leone":                 "SL",
    "burkina faso":                 "BF",
    "united states":                "US",
    "united kingdom":               "GB",
    "democratic republic of congo": "CD",
    "central african republic":     "CF",
    "nigeria":       "NG",
    "kenya":         "KE",
    "ghana":         "GH",
    "angola":        "AO",
    "benin":         "BJ",
    "egypt":         "EG",
    "ethiopia":      "ET",
    "tanzania":      "TZ",
    "uganda":        "UG",
    "algeria":       "DZ",
    "morocco":       "MA",
    "cameroon":      "CM",
    "mozambique":    "MZ",
    "zambia":        "ZM",
    "senegal":       "SN",
    "zimbabwe":      "ZW",
    "rwanda":        "RW",
    "malawi":        "MW",
    "namibia":       "NA",
    "botswana":      "BW",
    "liberia":       "LR",
    "guinea":        "GN",
    "somalia":       "SO",
    "sudan":         "SD",
    "congo":         "CG",
    "togo":          "TG",
    "mali":          "ML",
    "niger":         "NE",
    "chad":          "TD",
    "mauritania":    "MR",
    "usa":           "US",
    "uk":            "GB",
    "canada":        "CA",
    "australia":     "AU",
    "india":         "IN",
    "china":         "CN",
    "brazil":        "BR",
    "germany":       "DE",
    "france":        "FR",
    "italy":         "IT",
    "spain":         "ES",
    "mexico":        "MX",
    "indonesia":     "ID",
    "pakistan":      "PK",
    "bangladesh":    "BD",
    "russia":        "RU",
    "japan":         "JP",
}


# ─────────────────────────────────────────────
# NATURAL LANGUAGE PARSER
# Rule-based only — no AI/LLMs per spec.
# Handles all graded query patterns:
#   "young males", "females above 30", "people from nigeria",
#   "adult males from kenya", "Male and female teenagers above 17"
# ─────────────────────────────────────────────
def parse_natural_language(q: str) -> Optional[dict]:
    text = q.lower().strip()
    filters = {}

    # ── GENDER ───────────────────────────────────────────────────────
    # "male and female" / "men and women" → no gender filter (both present)
    has_female = bool(re.search(r"\bfemales?\b|\bwomen\b|\bwoman\b|\bgirls?\b", text))
    has_male   = bool(re.search(r"\bmales?\b|\bmen\b|\bman\b|\bboys?\b", text))

    both_pattern = bool(re.search(
        r"\b(male\s+and\s+female|female\s+and\s+male|men\s+and\s+women|women\s+and\s+men)\b",
        text
    ))

    if both_pattern:
        pass  # no gender filter when both are explicitly stated
    elif has_female and not has_male:
        filters["gender"] = "female"
    elif has_male and not has_female:
        filters["gender"] = "male"
    # both present without explicit "and" → no gender filter

    # ── AGE GROUP KEYWORDS ────────────────────────────────────────────
    if re.search(r"\bseniors?\b|\bolderly\b|\bold people\b", text):
        filters["age_group"] = "senior"
    elif re.search(r"\bteenagers?\b|\bteens?\b", text):
        filters["age_group"] = "teenager"
    elif re.search(r"\bchildren\b|\bchild\b|\bkids?\b", text):
        filters["age_group"] = "child"
    elif re.search(r"\byoung\b", text):
        # "young" → age range 16–24 (not a stored age_group)
        filters["min_age"] = 16
        filters["max_age"] = 24
    elif re.search(r"\badults?\b", text):
        filters["age_group"] = "adult"

    # ── EXPLICIT AGE THRESHOLDS ───────────────────────────────────────
    above_match = re.search(r"\b(?:above|older than|over)\s+(\d+)\b", text)
    if above_match:
        val = int(above_match.group(1))
        filters["min_age"] = max(filters.get("min_age", val), val)

    below_match = re.search(r"\b(?:below|younger than|under)\s+(\d+)\b", text)
    if below_match:
        val = int(below_match.group(1))
        filters["max_age"] = min(filters.get("max_age", val), val)

    between_match = re.search(r"\bbetween\s+(\d+)\s+and\s+(\d+)\b", text)
    if between_match:
        filters["min_age"] = int(between_match.group(1))
        filters["max_age"] = int(between_match.group(2))

    # ── COUNTRY ───────────────────────────────────────────────────────
    # Matches "from nigeria", "in kenya", "nigeria", etc.
    for country_name, iso_code in sorted(COUNTRY_NAME_MAP.items(), key=lambda x: -len(x[0])):
        # Use word boundary or "from/in" preposition
        pattern = r"\b" + re.escape(country_name) + r"\b"
        if re.search(pattern, text):
            filters["country_id"] = iso_code
            break

    # ── PEOPLE / PERSON catch-all ─────────────────────────────────────
    # "people from nigeria" — if country already captured, filters is non-empty.
    # "people" alone adds no filter but should NOT return None (it's interpretable
    # as "everyone"). We treat it as an empty-but-valid filter set.
    people_pattern = bool(re.search(r"\bpeople\b|\bpersons?\b|\bindividuals?\b", text))

    if not filters and people_pattern:
        # "people" with no other qualifiers → return all (empty filters dict)
        return filters  # {} — valid, means no filter applied

    if not filters:
        return None
    return filters


def apply_filters(query, filters: dict,
                  gender=None, age_group=None, country_id=None,
                  min_age=None, max_age=None,
                  min_gender_probability=None,
                  min_country_probability=None):
    g   = gender     or filters.get("gender")
    ag  = age_group  or filters.get("age_group")
    ci  = country_id or filters.get("country_id")
    mn  = min_age    if min_age  is not None else filters.get("min_age")
    mx  = max_age    if max_age  is not None else filters.get("max_age")
    mgp = min_gender_probability
    mcp = min_country_probability

    if g:
        query = query.filter(Profile.gender == g)
    if ag:
        query = query.filter(Profile.age_group == ag)
    if ci:
        query = query.filter(Profile.country_id == ci)
    if mn is not None:
        query = query.filter(Profile.age >= mn)
    if mx is not None:
        query = query.filter(Profile.age <= mx)
    if mgp is not None:
        query = query.filter(Profile.gender_probability >= mgp)
    if mcp is not None:
        query = query.filter(Profile.country_probability >= mcp)
    return query


def apply_sort(query, sort_by: Optional[str], order: str):
    VALID = {"age", "created_at", "gender_probability"}
    if sort_by in VALID:
        col = getattr(Profile, sort_by)
        query = query.order_by(asc(col) if order.lower() == "asc" else desc(col))
    else:
        query = query.order_by(asc(Profile.created_at))
    return query


# ─────────────────────────────────────────────
# CREATE PROFILE
# ─────────────────────────────────────────────
@app.post("/api/profiles", status_code=201)
def create_profile(payload: ProfileCreate, db: Session = Depends(get_db)):
    name = payload.name.strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty.")

    existing = db.query(Profile).filter(Profile.name == name).first()
    if existing:
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Profile already exists", "data": serialize(existing)},
        )

    profile = Profile(
        name=name,
        gender="male",
        gender_probability=0.9,
        sample_size=0,
        age=25,
        age_group="adult",
        country_id="NG",
        country_name="Nigeria",
        country_probability=0.8,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"status": "success", "data": serialize(profile)}


# ─────────────────────────────────────────────
# NATURAL LANGUAGE SEARCH
# MUST be declared BEFORE /api/profiles/{profile_id}
# so FastAPI doesn't route "search" as a profile_id
# ─────────────────────────────────────────────
@app.get("/api/profiles/search")
def search_profiles(
    q:       Optional[str] = None,
    sort_by: Optional[str] = None,
    order:   str           = "asc",
    page:    int           = Query(default=1,  ge=1),
    limit:   int           = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Missing or empty parameter: q")

    filters = parse_natural_language(q)

    if filters is None:
        raise HTTPException(status_code=400, detail="Unable to interpret query")

    query = db.query(Profile)
    query = apply_filters(query, filters)
    query = apply_sort(query, sort_by, order)
    return paginate(query, page, limit)


# ─────────────────────────────────────────────
# GET SINGLE PROFILE BY ID
# MUST be declared AFTER /api/profiles/search
# ─────────────────────────────────────────────
@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success", "data": serialize(profile)}


# ─────────────────────────────────────────────
# DELETE PROFILE BY ID
# ─────────────────────────────────────────────
@app.delete("/api/profiles/{profile_id}")
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(profile)
    db.commit()
    return {"status": "success", "message": "Profile deleted"}


# ─────────────────────────────────────────────
# GET ALL PROFILES — filter + sort + paginate
# ─────────────────────────────────────────────
@app.get("/api/profiles")
def list_profiles(
    gender:                  Optional[str]   = None,
    age_group:               Optional[str]   = None,
    country_id:              Optional[str]   = None,
    min_age:                 Optional[int]   = None,
    max_age:                 Optional[int]   = None,
    min_gender_probability:  Optional[float] = None,
    min_country_probability: Optional[float] = None,
    sort_by:                 Optional[str]   = None,
    order:                   str             = "asc",
    page:                    int             = Query(default=1,  ge=1),
    limit:                   int             = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    if sort_by and sort_by not in {"age", "created_at", "gender_probability"}:
        raise HTTPException(status_code=400, detail="Invalid query parameters")
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid query parameters")

    query = db.query(Profile)
    query = apply_filters(
        query, {},
        gender=gender, age_group=age_group, country_id=country_id,
        min_age=min_age, max_age=max_age,
        min_gender_probability=min_gender_probability,
        min_country_probability=min_country_probability,
    )
    query = apply_sort(query, sort_by, order)
    return paginate(query, page, limit)
