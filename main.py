"""
Insighta Labs+ Backend
Stage 2 + Stage 3 (Clean Single File Version)
"""

import csv
import io
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

# ✅ FIXED IMPORTS
from database import Profile, get_db, init_db
from models import User
from auth import (
    get_github_login_url, exchange_code_for_token, get_github_user,
    create_access_token, create_refresh_token, decode_token,
    get_current_user, require_admin, require_analyst,
    generate_state, get_or_create_user
)

# =========================
# ENV
# =========================
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

# =========================
# APP INIT (MUST COME FIRST)
# =========================
app = FastAPI(title="Insighta Labs+", version="3.0.0")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB INIT
@app.on_event("startup")
def startup():
    init_db()

# =========================
# REQUEST LOGGING
# =========================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    print(f"{request.method} {request.url}")
    return await call_next(request)

# =========================
# ERROR HANDLERS
# =========================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": exc.detail})

# =========================
# MODELS
# =========================
class ProfileCreate(BaseModel):
    name: str

class RoleUpdate(BaseModel):
    role: str

class RefreshRequest(BaseModel):
    refresh_token: str

# =========================
# HELPERS
# =========================
def serialize(p):
    return {
        "id": p.id,
        "name": p.name,
        "gender": p.gender,
        "age": p.age,
        "country_id": p.country_id,
        "created_at": p.created_at.isoformat(),
    }

def serialize_user(u):
    return {
        "id": u.id,
        "github_username": u.github_username,
        "role": u.role,
    }

def paginate(query, page, limit):
    total = query.count()
    rows = query.offset((page - 1) * limit).limit(limit).all()
    return {"status": "success", "page": page, "limit": limit, "total": total, "data": [serialize(r) for r in rows]}

# =========================
# AUTH (CLEAN)
# =========================
oauth_states = {}

@app.get("/auth/login")
@limiter.limit("20/minute")
async def login(request: Request):
    state = generate_state()
    return RedirectResponse(get_github_login_url(state))


@app.get("/auth/callback")
async def callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    try:
        verify_state(state)

        token_data = await exchange_code_for_token(code)
        if not token_data:
            raise HTTPException(status_code=400, detail="Token exchange failed")

        github_token = token_data.get("access_token")
        if not github_token:
            raise HTTPException(status_code=400, detail="No GitHub token")

        github_user = await get_github_user(github_token)
        if not github_user:
            raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")

        # ✅ VERY IMPORTANT
        user = get_or_create_user(db, github_user)

        access_token = create_access_token(user.id, user.role)
        refresh_token = create_refresh_token(user.id)

        # Optional (only if column exists)
        if hasattr(user, "refresh_token"):
            user.refresh_token = refresh_token
            db.commit()

        return {
            "status": "success",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 900
        }

    except Exception as e:
        print("🔥 CALLBACK ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/refresh")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    data = decode_token(payload.refresh_token)
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == data["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "access_token": create_access_token(user.id, user.role),
        "refresh_token": create_refresh_token(user.id)
    }

# =========================
# USERS (ADMIN)
# =========================
@app.get("/api/v1/users")
def users(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [serialize_user(u) for u in db.query(User).all()]

# =========================
# PROFILES V1 (PROTECTED)
# =========================
@app.get("/api/v1/profiles")
def profiles_v1(current_user: User = Depends(require_analyst),
                db: Session = Depends(get_db),
                page: int = 1, limit: int = 10):
    return paginate(db.query(Profile), page, limit)


@app.get("/api/v1/profiles/search")
def search_v1(q: str,
              current_user: User = Depends(require_analyst),
              db: Session = Depends(get_db)):
    return db.query(Profile).filter(Profile.name.ilike(f"%{q}%")).all()


@app.get("/api/v1/profiles/export")
def export(current_user: User = Depends(require_admin),
           db: Session = Depends(get_db)):
    profiles = db.query(Profile).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "gender", "age", "country_id"])
    for p in profiles:
        writer.writerow([p.id, p.name, p.gender, p.age, p.country_id])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv")

# =========================
# STAGE 2 LEGACY (UNCHANGED)
# =========================
@app.get("/api/profiles")
def profiles(db: Session = Depends(get_db)):
    return db.query(Profile).all()


@app.get("/api/profiles/search")
def search(q: str, db: Session = Depends(get_db)):
    return db.query(Profile).filter(Profile.name.ilike(f"%{q}%")).all()