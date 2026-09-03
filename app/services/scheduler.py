import logging
from datetime import datetime
from sqlalchemy import select

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.models import Job, AppConfig
from app.config import settings
from app.database import async_session_factory
from app.services.scraper.engine import scrape_orchestrator
from app.services.matcher import matcher_service
from app.services.notifier import notifier_service

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._scrape_job_id = "periodic_scrape"
        self._discovery_job_id = "periodic_discovery"

    def start(self):
        """Start the scheduler. Called during FastAPI startup."""
        interval_hours = getattr(settings, 'SCRAPE_INTERVAL_HOURS', 6)
        
        # Scrape + score + notify every N hours
        self.scheduler.add_job(
            self._run_scrape_pipeline,
            trigger=IntervalTrigger(hours=interval_hours),
            id=self._scrape_job_id,
            replace_existing=True
        )
        
        # Company re-discovery every 24 hours
        self.scheduler.add_job(
            self._run_discovery,
            trigger=IntervalTrigger(hours=24),
            id=self._discovery_job_id,
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info(f"Scheduler started. Scrape every {interval_hours}h, discovery every 24h.")

    def shutdown(self):
        """Shutdown scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")

    async def update_schedule(self, interval_hours: int):
        """Update the scrape interval."""
        if interval_hours <= 0:
            raise ValueError("Interval must be greater than 0")

        self.scheduler.add_job(
            self._run_scrape_pipeline,
            trigger=IntervalTrigger(hours=interval_hours),
            id=self._scrape_job_id,
            replace_existing=True
        )

        async with async_session_factory() as session:
            stmt = select(AppConfig).where(AppConfig.key == "scrape_interval_hours")
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            
            if config:
                config.value = str(interval_hours)
            else:
                session.add(AppConfig(key="scrape_interval_hours", value=str(interval_hours)))
            
            await session.commit()
            
        logger.info(f"Schedule updated to run every {interval_hours} hours.")

    def get_schedule_info(self) -> dict:
        """Return current schedule info."""
        job = self.scheduler.get_job(self._scrape_job_id)
        if not job:
            return {"status": "not_scheduled"}
            
        trigger = job.trigger
        interval_hours = None
        if isinstance(trigger, IntervalTrigger):
            interval_hours = trigger.interval.total_seconds() / 3600

        return {
            "status": "running" if self.scheduler.running else "stopped",
            "interval_hours": interval_hours,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
        }

    async def _run_discovery(self):
        """Periodic company re-discovery."""
        try:
            from app.services.company_discovery import run_discovery_pipeline
            created = await run_discovery_pipeline()
            logger.info(f"Periodic discovery created {created} new targets.")
        except Exception as e:
            logger.exception(f"Error during periodic discovery: {e}")

    async def _run_scrape_pipeline(self):
        """The full pipeline: scrape -> match -> notify."""
        logger.info("Starting scheduled scrape pipeline...")
        try:
            if getattr(scrape_orchestrator, 'is_running', False):
                logger.info("Scraper is already running. Skipping this cycle.")
                return
                
            new_jobs_count = await scrape_orchestrator.run_scrape(target_id=None)
            logger.info(f"Scrape completed. Found {new_jobs_count} new jobs.")

            scored_count = await matcher_service.score_new_jobs()
            logger.info(f"Matching completed. Scored {scored_count} jobs.")

            async with async_session_factory() as session:
                threshold = getattr(settings, 'MATCH_THRESHOLD', 70)
                stmt = select(Job).where(
                    Job.match_score >= threshold,
                    Job.status == 'new'
                )
                result = await session.execute(stmt)
                high_match_jobs = list(result.scalars().all())

            if high_match_jobs:
                notified_count = await notifier_service.notify_high_match_jobs(high_match_jobs)
                logger.info(f"Sent {notified_count} notifications for high-match jobs.")
            else:
                logger.info("No high-match jobs found to notify.")
                
        except Exception as e:
            logger.exception(f"Error occurred during scrape pipeline execution: {e}")

scheduler_service = SchedulerService()
