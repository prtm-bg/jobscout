from fastapi import APIRouter, Depends, Request, Form, HTTPException, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth import get_admin_creds, create_admin_user, verify_admin_user, create_session_token
from app.config import settings

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/setup")
async def setup_view(request: Request, db: AsyncSession = Depends(get_db)):
    stored_username, _ = await get_admin_creds(db)
    if stored_username:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request=request, name="setup.html", context={"request": request})

@router.post("/setup")
async def setup_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    stored_username, _ = await get_admin_creds(db)
    if stored_username:
        return RedirectResponse(url="/login", status_code=303)
        
    await create_admin_user(db, username, password)
    
    # Optionally login immediately
    token = create_session_token(username)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="session", 
        value=token, 
        httponly=True, 
        max_age=settings.SESSION_EXPIRY_HOURS * 3600,
        samesite="lax"
    )
    return response

@router.get("/login")
async def login_view(request: Request, db: AsyncSession = Depends(get_db)):
    stored_username, _ = await get_admin_creds(db)
    if not stored_username:
        return RedirectResponse(url="/setup", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request, "error": None})

@router.post("/login")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    is_valid = await verify_admin_user(db, username, password)
    if not is_valid:
        return templates.TemplateResponse(
            request=request, 
            name="login.html", 
            context={"request": request, "error": "Invalid username or password"}
        )
        
    token = create_session_token(username)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="session", 
        value=token, 
        httponly=True, 
        max_age=settings.SESSION_EXPIRY_HOURS * 3600,
        samesite="lax"
    )
    return response

@router.post("/logout")
async def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response
