from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, case

from app.database import get_db
from app.models import Job, ScrapeTarget, ScrapeRun
from app.services.scheduler import scheduler_service
from app.routers.settings import get_config
from app.config import settings as settings_module

from app.auth import get_current_user

router = APIRouter(tags=["dashboard"], dependencies=[Depends(get_current_user)])
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def dashboard(
    request: Request,
    min_score: int = 0,
    company: str = "",
    status: str = "",
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db)
):
    query = select(Job)
    
    if min_score:
        query = query.where(Job.match_score >= min_score)
    if company:
        query = query.where(Job.company.ilike(f"%{company}%"))
    if status:
        query = query.where(Job.status == status)
        
    # Get total count for pagination
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated jobs
    query = query.order_by(desc(Job.date_found)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    # Stats
    stats_result = await db.execute(
        select(
            func.count(Job.id).label('total'),
            func.sum(case((Job.status == 'new', 1), else_=0)).label('new'),
            func.sum(case((Job.status == 'applied', 1), else_=0)).label('applied')
        )
    )
    stats = stats_result.one()
    
    context = {
        "request": request,
        "jobs": jobs,
        "min_score": min_score,
        "company": company,
        "status": status,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "total_jobs": total,
        "stats": {
            "total": stats.total or 0,
            "new": stats.new or 0,
            "applied": stats.applied or 0
        }
    }
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request=request, name="partials/job_table.html", context=context)
        
    return templates.TemplateResponse(request=request, name="dashboard.html", context=context)

@router.get("/targets")
async def targets(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ScrapeTarget).order_by(ScrapeTarget.name))
    targets_list = result.scalars().all()
    
    context = {
        "request": request,
        "targets": targets_list
    }
    return templates.TemplateResponse(request=request, name="targets.html", context=context)

@router.get("/scheduler")
async def scheduler_view(request: Request, db: AsyncSession = Depends(get_db)):
    schedule_info = scheduler_service.get_schedule_info()
    
    result = await db.execute(
        select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(20)
    )
    recent_runs = result.scalars().all()
    
    context = {
        "request": request,
        "schedule_info": schedule_info,
        "recent_runs": recent_runs
    }
    return templates.TemplateResponse(request=request, name="scheduler.html", context=context)

@router.get("/settings")
async def settings_view(request: Request, db: AsyncSession = Depends(get_db)):
    # Load all config from DB, with fallbacks to .env
    resume_profile_raw = await get_config(db, "resume_profile")
    resume_profile = None
    if resume_profile_raw:
        try:
            resume_profile = __import__("json").loads(resume_profile_raw)
        except Exception:
            pass

    config = {
        "resume_text": await get_config(db, "resume_text"),
        "resume_profile": resume_profile,
        "preferred_countries": await get_config(db, "preferred_countries"),
        "apprise_urls": await get_config(db, "apprise_urls"),
        "match_threshold": await get_config(db, "notification_threshold", "70"),
        "proxy_list": await get_config(db, "proxy_list"),
        "captcha_provider": await get_config(db, "captcha_provider", "flaresolverr"),
        "captcha_api_key": await get_config(db, "captcha_api_key"),
        "ua_rotation_enabled": await get_config(db, "ua_rotation_enabled", "True"),
        "antibot_delay": await get_config(db, "antibot_delay", "2.0"),
        # LLM — prefer DB-saved values, fallback to .env
        "llm_provider": await get_config(db, "llm_provider") or settings_module.LLM_PROVIDER,
        "llm_model": await get_config(db, "llm_model") or settings_module.LLM_MODEL,
        "openai_api_key": await get_config(db, "openai_api_key") or settings_module.OPENAI_API_KEY,
        "openai_base_url": await get_config(db, "openai_base_url") or settings_module.OPENAI_BASE_URL,
        "gemini_api_key": await get_config(db, "gemini_api_key") or settings_module.GEMINI_API_KEY,
        "ollama_url": await get_config(db, "ollama_url") or settings_module.OLLAMA_URL,
        "last_discovery_at": await get_config(db, "last_discovery_at"),
    }
    
    context = {
        "request": request,
        "config": config,
    }
    return templates.TemplateResponse(request=request, name="settings.html", context=context)
