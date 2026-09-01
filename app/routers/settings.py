import json
from typing import Dict, Any, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AppConfig
from app.schemas import ScheduleConfig, AntiBotConfig, NotificationConfig
from app.services.scheduler import scheduler_service
from app.services.notifier import notifier_service

from app.auth import require_auth

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/templates")

async def get_config(session: AsyncSession, key: str, default: str = '') -> str:
    result = await session.execute(select(AppConfig).where(AppConfig.key == key))
    config = result.scalar_one_or_none()
    return config.value if config else default

async def set_config(session: AsyncSession, key: str, value: str):
    result = await session.execute(select(AppConfig).where(AppConfig.key == key))
    config = result.scalar_one_or_none()
    if config:
        config.value = value
    else:
        session.add(AppConfig(key=key, value=value))
    await session.commit()

class ResumePayload(BaseModel):
    resume_text: str

@router.get("/all")
async def get_all_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AppConfig))
    configs = result.scalars().all()
    return {c.key: c.value for c in configs}

@router.get("/resume")
async def get_resume(db: AsyncSession = Depends(get_db)):
    resume_text = await get_config(db, "resume_text")
    return {"resume_text": resume_text}

from fastapi import UploadFile, File

@router.post("/resume")
async def update_resume(
    request: Request,
    text: str = Form(..., alias="resume_text"),
    db: AsyncSession = Depends(get_db)
):
    await set_config(db, "resume_text", text)
    
    # Analyze and save profile
    from app.services.resume_parser import analyze_resume_profile
    profile = await analyze_resume_profile(text)
    await set_config(db, "resume_profile", profile)
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/toast.html",
            context={"request": request, "message": "Resume updated and analyzed", "type": "success"}
        )
        
    return {"message": "Resume updated"}

@router.post("/resume/upload")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    from app.services.resume_parser import extract_text_from_file, analyze_resume_profile
    
    text = await extract_text_from_file(file)
    await set_config(db, "resume_text", text)
    
    profile = await analyze_resume_profile(text)
    await set_config(db, "resume_profile", profile)
    
    if request.headers.get("HX-Request"):
        # Re-render the whole settings page or return a toast and refresh
        response = templates.TemplateResponse(
            request=request,
            name="partials/toast.html",
            context={"request": request, "message": "Resume uploaded and analyzed", "type": "success"}
        )
        response.headers["HX-Refresh"] = "true"
        return response
        
    return {"message": "Resume uploaded and analyzed"}

@router.post("/schedule")
async def update_schedule(
    request: Request,
    config: ScheduleConfig,
    db: AsyncSession = Depends(get_db)
):
    await scheduler_service.update_schedule(config.interval_hours)
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/toast.html",
            context={"request": request, "message": f"Schedule updated to every {config.interval_hours} hours", "type": "success"}
        )
        
    return {"message": "Schedule updated"}

@router.post("/notifications")
async def update_notifications(
    request: Request,
    config: NotificationConfig,
    db: AsyncSession = Depends(get_db)
):
    await set_config(db, "apprise_urls", config.apprise_urls)
    await set_config(db, "notification_threshold", str(config.min_score_threshold))
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/toast.html",
            context={"request": request, "message": "Notification settings updated", "type": "success"}
        )
        
    return {"message": "Notification settings updated"}

@router.post("/notifications/test")
async def test_notification(request: Request):
    success = await notifier_service.send_test_notification()
    
    if request.headers.get("HX-Request"):
        if success:
            return templates.TemplateResponse(
                request=request,
                name="partials/toast.html",
                context={"request": request, "message": "Test notification sent successfully", "type": "success"}
            )
        else:
            return templates.TemplateResponse(
                request=request,
                name="partials/toast.html",
                context={"request": request, "message": "Failed to send test notification", "type": "error"}
            )
            
    return {"success": success}

@router.post("/antibot")
async def update_antibot(
    request: Request,
    config: AntiBotConfig,
    db: AsyncSession = Depends(get_db)
):
    await set_config(db, "proxy_list", config.proxy_list)
    await set_config(db, "captcha_provider", config.captcha_provider)
    await set_config(db, "captcha_api_key", config.captcha_api_key)
    await set_config(db, "ua_rotation_enabled", str(config.ua_rotation_enabled))
    await set_config(db, "antibot_delay", str(config.delay_seconds))
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/toast.html",
            context={"request": request, "message": "Anti-bot settings updated", "type": "success"}
        )
        
    return {"message": "Anti-bot settings updated"}
