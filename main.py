from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import httpx
import asyncio
from sqlalchemy.orm import Session
from typing import Optional

from database import Profile, get_db

app = FastAPI(title="HNG Stage 1 - Profiles API")

# ── CORS — required for grading bot ──────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request schema ────────────────────────────────────────────────────────────
# Pydantic handles 422 automatically when name is wrong type (e.g. int, bool)
# 400 is handled manually for missing/empty string
class ProfileCreate(BaseModel):
    name: str


# ── External API calls ────────────────────────────────────────────────────────

async def call_genderize(name: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"https://api.genderize.io/?name={name}")
        r.raise_for_status()
        return r.json()


async def call_agify(name: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"https://api.agify.io/?name={name}")
        r.raise_for_status()
        return r.json()


async def call_nationalize(name: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"https://api.nationalize.io/?name={name}")
        r.raise_for_status()
        return r.json()


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_age_group(age: int) -> str:
    if age <= 12:
        return "child"
    elif age <= 19:
        return "teenager"
    elif age <= 59:
        return "adult"
    else:
        return "senior"


def fmt_datetime(dt) -> str:
    """Always return UTC ISO 8601 with Z suffix: 2026-04-01T12:00:00Z"""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def serialize_profile_full(p: Profile) -> dict:
    """Full profile — used in POST and GET /api/profiles/{id}"""
    return {
        "id": p.id,
        "name": p.name,
        "gender": p.gender,
        "gender_probability": p.gender_probability,
        "sample_size": p.sample_size,
        "age": p.age,
        "age_group": p.age_group,
        "country_id": p.country_id,
        "country_probability": p.country_probability,
        "created_at": fmt_datetime(p.created_at),
    }


def serialize_profile_list(p: Profile) -> dict:
    """Reduced fields — used in GET /api/profiles list"""
    return {
        "id": p.id,
        "name": p.name,
        "gender": p.gender,
        "age": p.age,
        "age_group": p.age_group,
        "country_id": p.country_id,
    }


# ── POST /api/profiles ────────────────────────────────────────────────────────

@app.post("/api/profiles", status_code=201)
async def create_profile(payload: ProfileCreate, db: Session = Depends(get_db)):

    # 400 — empty string after stripping
    name = payload.name.strip().lower()
    if not name:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "name cannot be empty"},
        )

    # Idempotency — return existing profile without calling external APIs
    existing = db.query(Profile).filter(Profile.name == name).first()
    if existing:
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Profile already exists",
                "data": serialize_profile_full(existing),
            },
        )

    # Call all 3 APIs concurrently
    try:
        gender_data, age_data, nation_data = await asyncio.gather(
            call_genderize(name),
            call_agify(name),
            call_nationalize(name),
        )
    except httpx.HTTPError:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "Failed to reach external APIs"},
        )

    # 502 — Genderize: gender is null OR count is 0
    if not gender_data.get("gender") or gender_data.get("count", 0) == 0:
        return JSONResponse(
            status_code=502,
            content={
                "status": "502",
                "message": "Genderize returned an invalid response",
            },
        )

    # 502 — Agify: age is null
    if age_data.get("age") is None:
        return JSONResponse(
            status_code=502,
            content={
                "status": "502",
                "message": "Agify returned an invalid response",
            },
        )

    # 502 — Nationalize: empty country list
    if not nation_data.get("country"):
        return JSONResponse(
            status_code=502,
            content={
                "status": "502",
                "message": "Nationalize returned an invalid response",
            },
        )

    # Pick country with highest probability
    best_country = max(nation_data["country"], key=lambda x: x["probability"])

    profile = Profile(
        name=name,
        gender=gender_data["gender"],
        gender_probability=round(float(gender_data["probability"]), 2),
        sample_size=int(gender_data["count"]),
        age=int(age_data["age"]),
        age_group=get_age_group(int(age_data["age"])),
        country_id=best_country["country_id"],
        country_probability=round(float(best_country["probability"]), 2),
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return JSONResponse(
        status_code=201,
        content={"status": "success", "data": serialize_profile_full(profile)},
    )


# ── GET /api/profiles/{id} ────────────────────────────────────────────────────

@app.get("/api/profiles/{profile_id}")
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Profile not found"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "success", "data": serialize_profile_full(profile)},
    )


# ── GET /api/profiles ─────────────────────────────────────────────────────────

@app.get("/api/profiles")
def list_profiles(
    gender: Optional[str] = Query(default=None),
    country_id: Optional[str] = Query(default=None),
    age_group: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Profile)

    # Case-insensitive filtering as required by spec
    if gender:
        query = query.filter(Profile.gender.ilike(gender.strip()))
    if country_id:
        query = query.filter(Profile.country_id.ilike(country_id.strip()))
    if age_group:
        query = query.filter(Profile.age_group.ilike(age_group.strip()))

    profiles = query.all()

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "count": len(profiles),
            "data": [serialize_profile_list(p) for p in profiles],
        },
    )


# ── DELETE /api/profiles/{id} ─────────────────────────────────────────────────

@app.delete("/api/profiles/{profile_id}", status_code=204)
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()

    if not profile:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Profile not found"},
        )

    db.delete(profile)
    db.commit()

    return Response(status_code=204)
