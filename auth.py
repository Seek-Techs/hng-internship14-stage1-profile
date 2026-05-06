import os
import secrets
import httpx
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import HTTPException, status, Request, Depends
from uuid6 import uuid7
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# import jwt
import time

from database import SessionLocal
from models import User


# ENV
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")
JWT_SECRET = os.getenv("JWT_SECRET")

# 🔥 OAuth state store (with expiry)


security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_analyst(user: User = Depends(get_current_user)):
    if user.role not in ["admin", "analyst"]:
        raise HTTPException(status_code=403, detail="Analyst access required")
    return user


def generate_state():
    payload = {
        "exp": int(time.time()) + 300,  # expires in 5 minutes
        "iat": int(time.time()),
        "nonce": secrets.token_urlsafe(16)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def validate_state(state: str):
    if state not in oauth_states:
        raise HTTPException(status_code=400, detail="Invalid state")

    # expire after 5 mins
    if (datetime.now(timezone.utc) - oauth_states[state]).seconds > 300:
        del oauth_states[state]
        raise HTTPException(status_code=400, detail="Expired state")

    del oauth_states[state]


def get_github_login_url(state: str):
    return (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=read:user user:email"
        f"&state={state}"
    )


async def exchange_code_for_token(code: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
        )
    return resp.json()


async def get_github_user(access_token: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"}
        )
    return resp.json()


def create_access_token(user_id: str, role: str):
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def create_refresh_token(user_id: str):
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode(
        {"sub": user_id, "type": "refresh", "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_or_create_user(github_user: dict):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.github_id == str(github_user["id"])).first()

        if not user:
            user = User(
                id=str(uuid7()),
                github_id=str(github_user["id"]),
                username=github_user.get("login"),
                role="analyst"
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        return user
    finally:
        db.close()


# 🔐 Cookie auth
def get_current_user_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(token)
    user_id = payload["sub"]

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()

    return user


# 🛡 CSRF
def verify_csrf(request: Request):
    cookie = request.cookies.get("csrf_token")
    header = request.headers.get("X-CSRF-Token")

    if not cookie or not header or cookie != header:
        raise HTTPException(status_code=403, detail="CSRF failed")

def verify_state(state: str):
    try:
        payload = jwt.decode(state, JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired state")