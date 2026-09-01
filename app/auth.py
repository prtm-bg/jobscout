from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AppConfig
from app.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_serializer():
    return URLSafeTimedSerializer(settings.SECRET_KEY)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

async def get_admin_creds(db: AsyncSession) -> tuple[str, str]:
    """Return (username, hashed_password) from AppConfig, or ('', '') if none."""
    result = await db.execute(select(AppConfig).where(AppConfig.key.in_(["admin_username", "admin_password"])))
    configs = {c.key: c.value for c in result.scalars().all()}
    return configs.get("admin_username", ""), configs.get("admin_password", "")

async def create_admin_user(db: AsyncSession, username: str, password: str):
    hashed = get_password_hash(password)
    db.add(AppConfig(key="admin_username", value=username))
    db.add(AppConfig(key="admin_password", value=hashed))
    await db.commit()

async def verify_admin_user(db: AsyncSession, username: str, password: str) -> bool:
    stored_username, stored_hashed_password = await get_admin_creds(db)
    if not stored_username or not stored_hashed_password:
        return False
    if username != stored_username:
        return False
    return verify_password(password, stored_hashed_password)

def create_session_token(username: str) -> str:
    serializer = get_serializer()
    return serializer.dumps({"username": username})

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    session_cookie = request.cookies.get("session")
    
    # Check if admin is set up at all
    stored_username, _ = await get_admin_creds(db)
    if not stored_username:
        # Need setup
        if request.url.path not in ["/setup", "/api/auth/setup", "/static/css/app.css"]:
            raise HTTPException(status_code=303, headers={"Location": "/setup"})
        return None

    if not session_cookie:
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Not authenticated")
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    serializer = get_serializer()
    try:
        # Max age in seconds
        data = serializer.loads(session_cookie, max_age=settings.SESSION_EXPIRY_HOURS * 3600)
        username = data.get("username")
        if username != stored_username:
            raise ValueError("Invalid user")
        return username
    except (SignatureExpired, BadSignature, ValueError):
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Session expired or invalid")
        raise HTTPException(status_code=303, headers={"Location": "/login"})

async def require_auth(user: str = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user
