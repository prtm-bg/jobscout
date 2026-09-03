"""
Settings router — all endpoints use Form(...) to match HTMX form submissions.
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AppConfig
from app.auth import require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/templates")


# ─── Helpers ────────────────────────────────────────────────────────────────────

async def get_config(session: AsyncSession, key: str, default: str = "") -> str:
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


def _toast(request, templates, message: str, toast_type: str = "success"):
    return templates.TemplateResponse(
        request=request,
        name="partials/toast.html",
        context={"request": request, "message": message, "type": toast_type},
    )


# ─── GET ────────────────────────────────────────────────────────────────────────

@router.get("/all")
async def get_all_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AppConfig))
    configs = result.scalars().all()
    return {c.key: c.value for c in configs}


@router.get("/resume")
async def get_resume(db: AsyncSession = Depends(get_db)):
    resume_text = await get_config(db, "resume_text")
    return {"resume_text": resume_text}


# ─── Resume Endpoints ──────────────────────────────────────────────────────────

async def _run_post_resume_pipeline(resume_text: str, db: AsyncSession):
    """After resume is saved: analyze profile, then trigger company discovery if countries are set."""
    from app.services.resume_parser import analyze_resume_profile
    from app.services.company_discovery import run_discovery_pipeline
    from app.services.scraper.engine import scrape_orchestrator
    from app.services.matcher import matcher_service

    # Step 1: Analyze resume → extract profile
    profile = await analyze_resume_profile(resume_text)
    await set_config(db, "resume_profile", profile)
    logger.info("Resume profile extracted.")

    # Step 2: If countries are set, discover companies + scrape + score
    countries = await get_config(db, "preferred_countries")
    if countries:
        logger.info("Countries set — running auto-discovery pipeline...")
        created = await run_discovery_pipeline()
        logger.info(f"Discovery created {created} new targets.")

        # Step 3: Scrape newly created targets
        new_jobs = await scrape_orchestrator.run_scrape()
        logger.info(f"Auto-scrape found {new_jobs} new jobs.")

        # Step 4: Score new jobs
        scored = await matcher_service.score_new_jobs()
        logger.info(f"Auto-scored {scored} jobs.")


@router.post("/resume")
async def update_resume(
    request: Request,
    resume_text: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await set_config(db, "resume_text", resume_text)

    # Run pipeline in background
    asyncio.create_task(_run_post_resume_pipeline(resume_text, db))

    if request.headers.get("HX-Request"):
        return _toast(request, templates, "Resume saved. Analyzing profile & discovering companies...")
    return {"message": "Resume updated"}


@router.post("/resume/upload")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    from app.services.resume_parser import extract_text_from_file

    text = await extract_text_from_file(file)
    await set_config(db, "resume_text", text)

    # Run pipeline in background
    asyncio.create_task(_run_post_resume_pipeline(text, db))

    if request.headers.get("HX-Request"):
        response = _toast(request, templates, "Resume uploaded. Analyzing & discovering companies...")
        response.headers["HX-Refresh"] = "true"
        return response
    return {"message": "Resume uploaded and analyzed"}


# ─── Preferences ────────────────────────────────────────────────────────────────

@router.post("/country")
async def update_country(
    request: Request,
    preferred_countries: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    await set_config(db, "preferred_countries", preferred_countries)

    # If we have a profile, trigger discovery
    profile = await get_config(db, "resume_profile")
    if profile and preferred_countries.strip():
        from app.services.company_discovery import run_discovery_pipeline
        asyncio.create_task(run_discovery_pipeline())

    if request.headers.get("HX-Request"):
        return _toast(request, templates, "Preferred countries updated. Discovering companies...")
    return {"message": "Countries updated"}


# ─── LLM Configuration ─────────────────────────────────────────────────────────

@router.post("/llm")
async def update_llm(
    request: Request,
    llm_provider: str = Form("gemini"),
    llm_model: str = Form("gemini-2.5-flash"),
    openai_api_key: str = Form(""),
    openai_base_url: str = Form(""),
    gemini_api_key: str = Form(""),
    ollama_url: str = Form("http://localhost:11434"),
    db: AsyncSession = Depends(get_db),
):
    await set_config(db, "llm_provider", llm_provider.lower())
    await set_config(db, "llm_model", llm_model)
    await set_config(db, "openai_api_key", openai_api_key)
    await set_config(db, "openai_base_url", openai_base_url)
    await set_config(db, "gemini_api_key", gemini_api_key)
    await set_config(db, "ollama_url", ollama_url)

    if request.headers.get("HX-Request"):
        return _toast(request, templates, "LLM configuration saved.")
    return {"message": "LLM config updated"}


# ─── Schedule ───────────────────────────────────────────────────────────────────

@router.post("/schedule")
async def update_schedule(
    request: Request,
    interval_hours: int = Form(6),
    db: AsyncSession = Depends(get_db),
):
    from app.services.scheduler import scheduler_service

    await scheduler_service.update_schedule(interval_hours)

    if request.headers.get("HX-Request"):
        return _toast(request, templates, f"Schedule updated to every {interval_hours} hours.")
    return {"message": "Schedule updated"}


# ─── Notifications ──────────────────────────────────────────────────────────────

@router.post("/notifications")
async def update_notifications(
    request: Request,
    apprise_urls: str = Form(""),
    match_threshold: int = Form(70),
    db: AsyncSession = Depends(get_db),
):
    await set_config(db, "apprise_urls", apprise_urls)
    await set_config(db, "notification_threshold", str(match_threshold))

    if request.headers.get("HX-Request"):
        return _toast(request, templates, "Notification settings saved.")
    return {"message": "Notification settings updated"}


@router.post("/notifications/test")
async def test_notification(request: Request):
    from app.services.notifier import notifier_service

    success = await notifier_service.send_test_notification()

    if request.headers.get("HX-Request"):
        msg = "Test notification sent!" if success else "Failed to send notification."
        return _toast(request, templates, msg, "success" if success else "error")
    return {"success": success}


# ─── Anti-Bot ───────────────────────────────────────────────────────────────────

@router.post("/antibot")
async def update_antibot(
    request: Request,
    proxy_list: str = Form(""),
    captcha_provider: str = Form("flaresolverr"),
    captcha_api_key: str = Form(""),
    ua_rotation_enabled: Optional[str] = Form(None),
    delay_seconds: float = Form(2.0),
    db: AsyncSession = Depends(get_db),
):
    await set_config(db, "proxy_list", proxy_list)
    await set_config(db, "captcha_provider", captcha_provider)
    await set_config(db, "captcha_api_key", captcha_api_key)
    await set_config(db, "ua_rotation_enabled", "True" if ua_rotation_enabled else "False")
    await set_config(db, "antibot_delay", str(delay_seconds))

    if request.headers.get("HX-Request"):
        return _toast(request, templates, "Anti-bot settings saved.")
    return {"message": "Anti-bot settings updated"}


# ─── Manual Pipeline Trigger ────────────────────────────────────────────────────

@router.post("/discover")
async def trigger_discovery(request: Request):
    """Manually trigger company discovery + scrape + score pipeline."""
    from app.services.company_discovery import run_discovery_pipeline
    from app.services.scraper.engine import scrape_orchestrator
    from app.services.matcher import matcher_service

    async def _pipeline():
        created = await run_discovery_pipeline()
        logger.info(f"Manual discovery created {created} targets.")
        new_jobs = await scrape_orchestrator.run_scrape()
        logger.info(f"Manual scrape found {new_jobs} jobs.")
        scored = await matcher_service.score_new_jobs()
        logger.info(f"Manual scoring completed {scored} jobs.")

    asyncio.create_task(_pipeline())

    if request.headers.get("HX-Request"):
        return _toast(request, templates, "Discovery pipeline started in background...")
    return {"message": "Pipeline triggered"}
