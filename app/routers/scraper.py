import asyncio
import logging
from typing import Optional, List
from pydantic import BaseModel

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db, async_session_factory
from app.models import ScrapeRun, Job
from app.schemas import ScrapeRunOut
from app.services.scraper.engine import scrape_orchestrator
from app.services.matcher import matcher_service
from app.services.notifier import notifier_service
from app.routers.settings import get_config

logger = logging.getLogger(__name__)

from app.auth import require_auth

router = APIRouter(prefix="/api/scraper", tags=["scraper"], dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/templates")

class ScrapeRequest(BaseModel):
    target_id: Optional[int] = None

async def run_full_pipeline(target_id: Optional[int] = None):
    try:
        # 1. Scrape
        jobs_found = await scrape_orchestrator.run_scrape(target_id=target_id)
        
        # 2. Match
        jobs_matched = await matcher_service.score_new_jobs()
        
        # 3. Notify
        async with async_session_factory() as session:
            threshold_str = await get_config(session, 'notification_threshold', '80')
            try:
                threshold = int(threshold_str)
            except ValueError:
                threshold = 80
                
            query = select(Job).where(
                Job.status == 'new',
                Job.match_score >= threshold
            )
            result = await session.execute(query)
            high_match_jobs = result.scalars().all()
            
            if high_match_jobs:
                await notifier_service.notify_high_match_jobs(high_match_jobs)
                # Mark as notified or keep as new depending on design
                # We'll leave as new for now
                
    except Exception as e:
        logger.error(f"Pipeline error: {e}")

@router.post("/run")
async def run_scraper(request: ScrapeRequest = None):
    if scrape_orchestrator.is_running:
        raise HTTPException(status_code=409, detail="Scraper is already running")
        
    target_id = request.target_id if request else None
    
    # Launch background task
    asyncio.create_task(run_full_pipeline(target_id))
    
    return {"status": "started", "message": "Scrape initiated"}

@router.get("/status")
async def get_status():
    return {
        "status": "running" if scrape_orchestrator.is_running else "idle",
        "is_running": scrape_orchestrator.is_running
    }

@router.get("/runs", response_model=List[ScrapeRunOut])
async def list_runs(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(20)
    )
    runs = result.scalars().all()
    
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="partials/runs_table.html", # Assuming a runs table partial exists or just mapping correctly
            context={"request": request, "recent_runs": runs}
        )
        
    return runs
