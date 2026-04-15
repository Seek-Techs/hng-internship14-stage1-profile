from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import asyncio
from sqlalchemy.orm import Session
from datetime import datetime
# import uuid7

from database import Profile, get_db
from schemas import ProfileCreate, ProfileResponse, ErrorResponse

app = FastAPI(title="HNG Stage 1 - Profiles API")

# CORS - Very Important for grading bot
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def call_genderize(name: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.genderize.io/?name={name}")
        return r.json()


async def call_agify(name: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.agify.io/?name={name}")
        return r.json()


async def call_nationalize(name: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"https://api.nationalize.io/?name={name}")
        return r.json()


def get_age_group(age: int) -> str:
    if age <= 12:
        return "child"
    elif age <= 19:
        return "teenager"
    elif age <= 59:
        return "adult"
    else:
        return "senior"


@app.post("/api/profiles")
async def create_profile(payload: ProfileCreate, db: Session = Depends(get_db)):
    
    # ====================== VALIDATION FIRST ======================
    if payload.name is None:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "name parameter is required"}
        )

    name = str(payload.name).strip().lower()

    if not name:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "name cannot be empty"}
        )

    if len(name) > 100:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "name is too long (max 100 characters)"}
        )
    # ============================================================

    # Now check idempotency (only for valid names)
    existing = db.query(Profile).filter(Profile.name == name).first()
    if existing:
        return {
            "status": "success",
            "message": "Profile already exists",
            "data": {
                "id": existing.id,
                "name": existing.name,
                "gender": existing.gender,
                "gender_probability": existing.gender_probability,
                "sample_size": existing.sample_size,
                "age": existing.age,
                "age_group": existing.age_group,
                "country_id": existing.country_id,
                "country_probability": existing.country_probability,
                "created_at": existing.created_at.isoformat().replace("+00:00", "Z")
            }
        }

    # ... rest of your code (API calls, processing, etc.) remains the same

    try:
        # Call 3 APIs concurrently
        gender_data, age_data, nation_data = await asyncio.gather(
            call_genderize(name),
            call_agify(name),
            call_nationalize(name)
        )
        # Debug: Print errors
        print("Genderize:", gender_data)
        print("Agify:", age_data)
        print("Nationalize:", nation_data)

        # Check for exceptions
        if isinstance(gender_data, Exception) or isinstance(age_data, Exception) or isinstance(nation_data, Exception):
            raise Exception("One or more APIs failed")

        # Edge Cases
        if not gender_data.get("gender") or gender_data.get("count", 0) == 0:
            return JSONResponse(status_code=422, content={
                "status": "error", 
                "message": "No prediction available for the provided name"
            })

        if age_data.get("age") is None:
            return JSONResponse(status_code=422, content={
                "status": "error", 
                "message": "Could not determine age"
            })

        if not nation_data.get("country"):
            return JSONResponse(status_code=422, content={
                "status": "error", 
                "message": "Could not determine country"
            })

        # Best country
        best_country = max(nation_data["country"], key=lambda x: x["probability"])

        # Create Profile
        profile = Profile(
            name=name,
            gender=gender_data["gender"],
            gender_probability=round(float(gender_data["probability"]), 2),
            sample_size=int(gender_data["count"]),
            age=int(age_data["age"]),
            age_group=get_age_group(age_data["age"]),
            country_id=best_country["country_id"],
            country_probability=round(float(best_country["probability"]), 2),
        )

        db.add(profile)
        db.commit()
        db.refresh(profile)

        return {
            "status": "success",
            "data": {
                "id": profile.id,
                "name": profile.name,
                "gender": profile.gender,
                "gender_probability": profile.gender_probability,
                "sample_size": profile.sample_size,
                "age": profile.age,
                "age_group": profile.age_group,
                "country_id": profile.country_id,
                "country_probability": profile.country_probability,
                "created_at": profile.created_at.isoformat().replace("+00:00", "Z")
            }
        }

    except Exception as e:
        print("Error occurred:", str(e))   # For debugging
        return JSONResponse(status_code=502, content={
            "status": "error",
            "message": "Failed to fetch data from external APIs"
        })