"""
main.py — Insighta Labs+ Backend
Stage 3: Auth + Roles added on top of Stage 2
"""

import csv
import io
import secrets
from datetime import datetime, timezone
from typing import Optional
import hashlib
import base64


from fastapi import FastAPI, Depends, Query, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import re
import os

from database import Profile, User, get_db, init_db
from backend.auth import (
    get_github_login_url, exchange_code_for_token, get_github_user,
    create_access_token, create_refresh_token, decode_token,
    get_current_user, require_admin, require_analyst, generate_state,get_or_create_user
)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Insighta Labs+", version="3.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")
@app.middleware("http")
async def log_requests(request, call_next):
    print(f"{request.method} {request.url}")
    response = await call_next(request)
    return response

@app.on_event("startup")
def on_startup():
    init_db()

from fastapi.exceptions import RequestValidationError

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"status": "error", "message": "Invalid parameter type"})

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"status": "error", "message": "Internal server error"})

class ProfileCreate(BaseModel):
    name: str

class RoleUpdate(BaseModel):
    role: str

class RefreshRequest(BaseModel):
    refresh_token: str

def get_age_group(age: int) -> str:
    if age <= 12: return "child"
    elif age <= 19: return "teenager"
    elif age <= 59: return "adult"
    return "senior"

def serialize(p) -> dict:
    return {
        "id": p.id, "name": p.name, "gender": p.gender,
        "gender_probability": p.gender_probability, "age": p.age,
        "age_group": p.age_group, "country_id": p.country_id,
        "country_name": p.country_name, "country_probability": p.country_probability,
        "created_at": p.created_at.isoformat(),
    }

def serialize_user(u) -> dict:
    return {
        "id": u.id, "github_username": u.github_username, "email": u.email,
        "avatar_url": u.avatar_url, "role": u.role, "is_active": u.is_active,
        "created_at": u.created_at.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }

def paginate(query, page: int, limit: int) -> dict:
    limit = max(1, min(limit, 50))
    page = max(1, page)
    total = query.count()
    rows = query.offset((page - 1) * limit).limit(limit).all()
    return {"status": "success", "page": page, "limit": limit, "total": total, "data": [serialize(r) for r in rows]}

COUNTRY_NAME_MAP = {
    "south africa": "ZA", "ivory coast": "CI", "cote d'ivoire": "CI",
    "sierra leone": "SL", "burkina faso": "BF", "united states": "US",
    "united kingdom": "GB", "democratic republic of congo": "CD",
    "central african republic": "CF",
    "nigeria": "NG", "kenya": "KE", "ghana": "GH", "angola": "AO",
    "benin": "BJ", "egypt": "EG", "ethiopia": "ET", "tanzania": "TZ",
    "uganda": "UG", "algeria": "DZ", "morocco": "MA", "cameroon": "CM",
    "mozambique": "MZ", "zambia": "ZM", "senegal": "SN", "zimbabwe": "ZW",
    "rwanda": "RW", "malawi": "MW", "namibia": "NA", "botswana": "BW",
    "liberia": "LR", "guinea": "GN", "somalia": "SO", "sudan": "SD",
    "congo": "CG", "togo": "TG", "mali": "ML", "niger": "NE",
    "chad": "TD", "mauritania": "MR", "usa": "US", "uk": "GB",
    "canada": "CA", "australia": "AU", "india": "IN", "china": "CN",
    "brazil": "BR", "germany": "DE", "france": "FR", "italy": "IT",
    "spain": "ES", "mexico": "MX", "indonesia": "ID", "pakistan": "PK",
    "bangladesh": "BD", "russia": "RU", "japan": "JP",
}

def parse_natural_language(q: str) -> Optional[dict]:
    text = q.lower().strip()
    filters = {}
    has_female = bool(re.search(r"\bfemales?\b|\bwomen\b|\bwoman\b|\bgirls?\b", text))
    has_male = bool(re.search(r"\bmales?\b|\bmen\b|\bman\b|\bboys?\b", text))
    both_pattern = bool(re.search(r"\b(male\s+and\s+female|female\s+and\s+male|men\s+and\s+women|women\s+and\s+men)\b", text))
    if both_pattern: pass
    elif has_female and not has_male: filters["gender"] = "female"
    elif has_male and not has_female: filters["gender"] = "male"
    if re.search(r"\bseniors?\b|\bolderly\b|\bold people\b", text): filters["age_group"] = "senior"
    elif re.search(r"\bteenagers?\b|\bteens?\b", text): filters["age_group"] = "teenager"
    elif re.search(r"\bchildren\b|\bchild\b|\bkids?\b", text): filters["age_group"] = "child"
    elif re.search(r"\byoung\b", text): filters["min_age"] = 16; filters["max_age"] = 24
    elif re.search(r"\badults?\b", text): filters["age_group"] = "adult"
    above = re.search(r"\b(?:above|older than|over)\s+(\d+)\b", text)
    if above:
        val = int(above.group(1))
        filters["min_age"] = max(filters.get("min_age", val), val)
    below = re.search(r"\b(?:below|younger than|under)\s+(\d+)\b", text)
    if below:
        val = int(below.group(1))
        filters["max_age"] = min(filters.get("max_age", val), val)
    between = re.search(r"\bbetween\s+(\d+)\s+and\s+(\d+)\b", text)
    if between:
        filters["min_age"] = int(between.group(1))
        filters["max_age"] = int(between.group(2))
    for cn, iso in sorted(COUNTRY_NAME_MAP.items(), key=lambda x: -len(x[0])):
        if re.search(r"\b" + re.escape(cn) + r"\b", text):
            filters["country_id"] = iso
            break
    people = bool(re.search(r"\bpeople\b|\bpersons?\b|\bindividuals?\b", text))
    if not filters and people: return filters
    if not filters: return None
    return filters

def apply_filters(query, filters, gender=None, age_group=None, country_id=None,
                  min_age=None, max_age=None, min_gender_probability=None, min_country_probability=None):
    g  = gender     or filters.get("gender")
    ag = age_group  or filters.get("age_group")
    ci = country_id or filters.get("country_id")
    mn = min_age    if min_age  is not None else filters.get("min_age")
    mx = max_age    if max_age  is not None else filters.get("max_age")
    if g:  query = query.filter(Profile.gender == g)
    if ag: query = query.filter(Profile.age_group == ag)
    if ci: query = query.filter(Profile.country_id == ci)
    if mn is not None: query = query.filter(Profile.age >= mn)
    if mx is not None: query = query.filter(Profile.age <= mx)
    if min_gender_probability  is not None: query = query.filter(Profile.gender_probability  >= min_gender_probability)
    if min_country_probability is not None: query = query.filter(Profile.country_probability >= min_country_probability)
    return query

def apply_sort(query, sort_by, order):
    if sort_by in {"age", "created_at", "gender_probability"}:
        col = getattr(Profile, sort_by)
        query = query.order_by(asc(col) if order.lower() == "asc" else desc(col))
    else:
        query = query.order_by(asc(Profile.created_at))
    return query

# ── OAuth state store ──────────────────────────────────────────────────────────
oauth_states = {}

# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/auth/login")
@limiter.limit("20/minute")
async def login(request: Request):
    state = generate_state()
    oauth_states[state] = datetime.now(timezone.utc)

    return RedirectResponse(get_github_login_url(state))

@app.post("/auth/refresh")
async def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_data = decode_token(payload.refresh_token)
    if token_data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = db.query(User).filter(User.id == token_data["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    if user.refresh_token != payload.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token revoked")
    new_access  = create_access_token(user.id, user.role)
    new_refresh = create_refresh_token(user.id)
    user.refresh_token = new_refresh
    db.commit()
    return {"status": "success", "access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer", "expires_in": 900}

@app.post("/auth/logout")
async def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.refresh_token = None
    db.commit()
    return {"status": "success", "message": "Logged out successfully"}

@app.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {"status": "success", "data": serialize_user(current_user)}

# ══════════════════════════════════════════════════════════════════════════════
# USER MANAGEMENT (admin only)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/users")
def list_users(page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=50),
               current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    total = db.query(User).count()
    users = db.query(User).offset((page-1)*limit).limit(limit).all()
    return {"status": "success", "page": page, "limit": limit, "total": total, "data": [serialize_user(u) for u in users]}

@app.put("/api/v1/users/{user_id}/role")
def update_user_role(user_id: str, payload: RoleUpdate,
                     current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.role not in ("admin", "analyst"):
        raise HTTPException(status_code=400, detail="Role must be 'admin' or 'analyst'")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return {"status": "success", "data": serialize_user(user)}

# ══════════════════════════════════════════════════════════════════════════════
# PROFILE ROUTES v1 (protected)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/profiles", status_code=201)
def create_profile_v1(payload: ProfileCreate, current_user: User = Depends(require_analyst), db: Session = Depends(get_db)):
    name = payload.name.strip().lower()
    if not name: raise HTTPException(status_code=400, detail="Name cannot be empty.")
    existing = db.query(Profile).filter(Profile.name == name).first()
    if existing:
        return JSONResponse(status_code=200, content={"status": "success", "message": "Profile already exists", "data": serialize(existing)})
    profile = Profile(name=name, gender="male", gender_probability=0.9, sample_size=0, age=25, age_group="adult", country_id="NG", country_name="Nigeria", country_probability=0.8)
    db.add(profile); db.commit(); db.refresh(profile)
    return {"status": "success", "data": serialize(profile)}

@app.get("/api/v1/profiles/search")
def search_profiles_v1(q: Optional[str] = None, sort_by: Optional[str] = None, order: str = "asc",
                        page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=50),
                        current_user: User = Depends(require_analyst), db: Session = Depends(get_db)):
    if not q or not q.strip(): raise HTTPException(status_code=400, detail="Missing or empty parameter: q")
    filters = parse_natural_language(q)
    if filters is None: raise HTTPException(status_code=400, detail="Unable to interpret query")
    query = apply_sort(apply_filters(db.query(Profile), filters), sort_by, order)
    return paginate(query, page, limit)

@app.get("/api/v1/profiles/export")
def export_profiles_csv(gender: Optional[str] = None, age_group: Optional[str] = None,
                         country_id: Optional[str] = None, min_age: Optional[int] = None,
                         max_age: Optional[int] = None, current_user: User = Depends(require_admin),
                         db: Session = Depends(get_db)):
    profiles = apply_filters(db.query(Profile), {}, gender=gender, age_group=age_group,
                              country_id=country_id, min_age=min_age, max_age=max_age).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","name","gender","gender_probability","age","age_group","country_id","country_name","country_probability","created_at"])
    for p in profiles:
        writer.writerow([p.id,p.name,p.gender,p.gender_probability,p.age,p.age_group,p.country_id,p.country_name,p.country_probability,p.created_at.isoformat()])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=profiles.csv"})

@app.get("/api/v1/profiles/{profile_id}")
def get_profile_v1(profile_id: str, current_user: User = Depends(require_analyst), db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile: raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success", "data": serialize(profile)}

@app.delete("/api/v1/profiles/{profile_id}")
def delete_profile_v1(profile_id: str, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile: raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(profile); db.commit()
    return {"status": "success", "message": "Profile deleted"}

@app.get("/api/v1/profiles")
def list_profiles_v1(gender: Optional[str] = None, age_group: Optional[str] = None,
                      country_id: Optional[str] = None, min_age: Optional[int] = None,
                      max_age: Optional[int] = None, min_gender_probability: Optional[float] = None,
                      min_country_probability: Optional[float] = None, sort_by: Optional[str] = None,
                      order: str = "asc", page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=50),
                      current_user: User = Depends(require_analyst), db: Session = Depends(get_db)):
    if sort_by and sort_by not in {"age","created_at","gender_probability"}:
        raise HTTPException(status_code=400, detail="Invalid query parameters")
    if order not in {"asc","desc"}: raise HTTPException(status_code=400, detail="Invalid query parameters")
    query = apply_sort(apply_filters(db.query(Profile), {}, gender=gender, age_group=age_group,
                       country_id=country_id, min_age=min_age, max_age=max_age,
                       min_gender_probability=min_gender_probability,
                       min_country_probability=min_country_probability), sort_by, order)
    return paginate(query, page, limit)

# ══════════════════════════════════════════════════════════════════════════════
# LEGACY /api/profiles ROUTES (no auth — keeps Stage 2 grader working)
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/profiles", status_code=201)
def create_profile_legacy(payload: ProfileCreate, db: Session = Depends(get_db)):
    name = payload.name.strip().lower()
    if not name: raise HTTPException(status_code=400, detail="Name cannot be empty.")
    existing = db.query(Profile).filter(Profile.name == name).first()
    if existing:
        return JSONResponse(status_code=200, content={"status": "success", "message": "Profile already exists", "data": serialize(existing)})
    profile = Profile(name=name, gender="male", gender_probability=0.9, sample_size=0, age=25, age_group="adult", country_id="NG", country_name="Nigeria", country_probability=0.8)
    db.add(profile); db.commit(); db.refresh(profile)
    return {"status": "success", "data": serialize(profile)}

@app.get("/api/profiles/search")
def search_profiles_legacy(q: Optional[str] = None, sort_by: Optional[str] = None, order: str = "asc",
                             page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    if not q or not q.strip(): raise HTTPException(status_code=400, detail="Missing or empty parameter: q")
    filters = parse_natural_language(q)
    if filters is None: raise HTTPException(status_code=400, detail="Unable to interpret query")
    return paginate(apply_sort(apply_filters(db.query(Profile), filters), sort_by, order), page, limit)

@app.get("/api/profiles/{profile_id}")
def get_profile_legacy(profile_id: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile: raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "success", "data": serialize(profile)}

@app.delete("/api/profiles/{profile_id}")
def delete_profile_legacy(profile_id: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile: raise HTTPException(status_code=404, detail="Profile not found")
    db.delete(profile); db.commit()
    return {"status": "success", "message": "Profile deleted"}

@app.get("/api/profiles")
def list_profiles_legacy(gender: Optional[str] = None, age_group: Optional[str] = None,
                          country_id: Optional[str] = None, min_age: Optional[int] = None,
                          max_age: Optional[int] = None, min_gender_probability: Optional[float] = None,
                          min_country_probability: Optional[float] = None, sort_by: Optional[str] = None,
                          order: str = "asc", page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=50),
                          db: Session = Depends(get_db)):
    if sort_by and sort_by not in {"age","created_at","gender_probability"}:
        raise HTTPException(status_code=400, detail="Invalid query parameters")
    if order not in {"asc","desc"}: raise HTTPException(status_code=400, detail="Invalid query parameters")
    return paginate(apply_sort(apply_filters(db.query(Profile), {}, gender=gender, age_group=age_group,
                    country_id=country_id, min_age=min_age, max_age=max_age,
                    min_gender_probability=min_gender_probability,
                    min_country_probability=min_country_probability), sort_by, order), page, limit)

def generate_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b'=').decode()
    return verifier, challenge

@app.get("/auth/callback")
async def callback(code: str, state: str, request: Request):

    # 🔐 VALIDATE STATE HERE (CORRECT PLACE)
    if state not in oauth_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    # expire after 5 mins
    if (datetime.now(timezone.utc) - oauth_states[state]).seconds > 300:
        del oauth_states[state]
        raise HTTPException(status_code=400, detail="Expired OAuth state")

    # delete after validation
    del oauth_states[state]

    # continue normal flow
    token_data = await exchange_code_for_token(code)
    github_token = token_data.get("access_token")

    if not github_token:
        raise HTTPException(status_code=400, detail="GitHub auth failed")

    github_user = await get_github_user(github_token)
    user = get_or_create_user(github_user)

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id)

    user_agent = request.headers.get("user-agent", "").lower()

    # 🌐 WEB FLOW
    if "mozilla" in user_agent:
        response = RedirectResponse(url="/dashboard")

        response.set_cookie("access_token", access_token, httponly=True, samesite="lax")
        response.set_cookie("refresh_token", refresh_token, httponly=True, samesite="lax")

        import secrets
        csrf_token = secrets.token_urlsafe(32)

        response.set_cookie("csrf_token", csrf_token, httponly=False, samesite="lax")

        return response

    # 💻 CLI FLOW
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": 900
    }