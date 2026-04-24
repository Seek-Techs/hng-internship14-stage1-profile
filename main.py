from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc
from typing import Optional
import re

from database import Profile, get_db, init_db

app = FastAPI()

# ✅ FIX: Proper CORS (required by HNG)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ FIX: DB init
@app.on_event("startup")
def on_startup():
    init_db()

# ─────────────────────────────────────────────
# GLOBAL ERROR HANDLERS (HNG FORMAT)
# ─────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": exc.detail},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Invalid parameter type"},
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"},
    )

# ─────────────────────────────────────────────
# SERIALIZER
# ─────────────────────────────────────────────
def serialize(p):
    return {
        "id": str(p.id),
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

# ─────────────────────────────────────────────
# PAGINATION
# ─────────────────────────────────────────────
def paginate(query, page: int, limit: int):
    limit = max(1, min(limit, 50))
    offset = (page - 1) * limit

    total = query.count()
    results = query.offset(offset).limit(limit).all()

    return {
        "status": "success",
        "page": page,
        "limit": limit,
        "total": total,
        "data": [serialize(r) for r in results],
    }

# ─────────────────────────────────────────────
# NLP PARSER (SINGLE SOURCE OF TRUTH)
# ─────────────────────────────────────────────
COUNTRY_MAP = {
    "south africa":                 "ZA",
    "ivory coast":                  "CI",
    "cote d'ivoire":                "CI",
    "sierra leone":                 "SL",
    "burkina faso":                 "BF",
    "united states":                "US",
    "united kingdom":               "GB",
    "democratic republic of congo": "CD",
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

def parse_query(q: str):
    q = q.lower().strip()
    filters = {}

    # ─────────────────────────────
    # GENDER (handles plural + both)
    # ─────────────────────────────
    has_male = "male" in q or "males" in q
    has_female = "female" in q or "females" in q

    if has_male and not has_female:
        filters["gender"] = "male"
    elif has_female and not has_male:
        filters["gender"] = "female"
    # if both → don't filter gender

    # ─────────────────────────────
    # AGE GROUPS
    # ─────────────────────────────
    if "child" in q:
        filters["age_group"] = "child"

    elif "teenager" in q or "teenagers" in q:
        filters["age_group"] = "teenager"

    elif "adult" in q or "adults" in q:
        filters["age_group"] = "adult"

    elif "senior" in q or "seniors" in q:
        filters["age_group"] = "senior"

    # ─────────────────────────────
    # "young" special rule (16–24)
    # ─────────────────────────────
    if "young" in q:
        filters["min_age"] = 16
        filters["max_age"] = 24

    # ─────────────────────────────
    # AGE CONDITIONS
    # ─────────────────────────────
    import re

    above = re.search(r"(above|over)\s+(\d+)", q)
    if above:
        filters["min_age"] = int(above.group(2))

    below = re.search(r"(below|under)\s+(\d+)", q)
    if below:
        filters["max_age"] = int(below.group(2))

    for name, code in COUNTRY_MAP.items():
        if name in q:
            filters["country_id"] = code
            break

    # ─────────────────────────────
    # FINAL VALIDATION
    # ─────────────────────────────
    if not filters:
        return None

    return filters

# ─────────────────────────────────────────────
# APPLY FILTERS
# ─────────────────────────────────────────────
def apply_filters(query, filters):
    if "gender" in filters:
        query = query.filter(Profile.gender == filters["gender"])

    if "age_group" in filters:
        query = query.filter(Profile.age_group == filters["age_group"])

    if "country_id" in filters:
        query = query.filter(Profile.country_id == filters["country_id"])

    if "min_age" in filters:
        query = query.filter(Profile.age >= filters["min_age"])

    if "max_age" in filters:
        query = query.filter(Profile.age <= filters["max_age"])

    return query

# ─────────────────────────────────────────────
# SORTING
# ─────────────────────────────────────────────
def apply_sort(query, sort_by, order):
    if sort_by not in {"age", "created_at", "gender_probability"}:
        return query

    col = getattr(Profile, sort_by)
    return query.order_by(asc(col) if order == "asc" else desc(col))

# ─────────────────────────────────────────────
# MAIN ENDPOINT
# ─────────────────────────────────────────────
@app.get("/api/profiles")
def get_profiles(
    gender: Optional[str] = None,
    age_group: Optional[str] = None,
    country_id: Optional[str] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    sort_by: Optional[str] = None,
    order: str = "asc",
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    if order not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="Invalid query parameters")

    query = db.query(Profile)

    filters = {
        "gender": gender,
        "age_group": age_group,
        "country_id": country_id,
        "min_age": min_age,
        "max_age": max_age,
    }

    query = apply_filters(query, {k: v for k, v in filters.items() if v is not None})
    query = apply_sort(query, sort_by, order)

    return paginate(query, page, limit)

# ─────────────────────────────────────────────
# NLP SEARCH (ONLY ONE VERSION — FIXED)
# ─────────────────────────────────────────────
@app.get("/api/profiles/search")
def search_profiles(
    q: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    if not q:
        raise HTTPException(status_code=400, detail="Missing or empty parameter")

    filters = parse_query(q)

    if filters is None:
        raise HTTPException(
            status_code=400,
            detail="Unable to interpret query"
        )

    query = db.query(Profile)
    query = apply_filters(query, filters)

    return paginate(query, page, limit)
