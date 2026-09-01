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

    def start(self):
        """Start the scheduler. Called during FastAPI startup."""
        interval_hours = getattr(settings, 'SCRAPE_INTERVAL_HOURS', 12)
        
        self.scheduler.add_job(
            self._run_scrape_pipeline,
            trigger=IntervalTrigger(hours=interval_hours),
            id=self._scrape_job_id,
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info(f"Scheduler started. Scrape pipeline scheduled every {interval_hours} hours.")

    def shutdown(self):
        """Shutdown scheduler. Called during FastAPI shutdown."""
        self.scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down.")

    async def update_schedule(self, interval_hours: int):
        """Update the scrape interval."""
        if interval_hours <= 0:
            raise ValueError("Interval must be greater than 0")

        # Update APScheduler job
        self.scheduler.add_job(
            self._run_scrape_pipeline,
            trigger=IntervalTrigger(hours=interval_hours),
            id=self._scrape_job_id,
            replace_existing=True
        )

        # Persist to AppConfig table
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
        """Return current schedule info: interval, next_run_time, etc."""
        job = self.scheduler.get_job(self._scrape_job_id)
        if not job:
            return {"status": "not_scheduled"}
            
        trigger = job.trigger
        interval_hours = None
        if isinstance(trigger, IntervalTrigger):
            # Extract hours from timedelta (assuming trigger.interval is a timedelta)
            interval_hours = trigger.interval.total_seconds() / 3600

        return {
            "status": "running" if self.scheduler.running else "stopped",
            "interval_hours": interval_hours,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None
        }

    async def _run_scrape_pipeline(self):
        """The full pipeline: scrape -> match -> notify."""
        logger.info("Starting scheduled scrape pipeline...")
        try:
            # 1. Run scraper
            if getattr(scrape_orchestrator, 'is_running', False):
                logger.info("Scraper is already running. Skipping this cycle.")
                return
                
            new_jobs_count = await scrape_orchestrator.run_scrape(target_id=None)
            logger.info(f"Scrape completed. Found {new_jobs_count} new jobs.")

            # 2. Score new jobs
            scored_count = await matcher_service.score_new_jobs()
            logger.info(f"Matching completed. Scored {scored_count} jobs.")

            # 3. Get newly scored high-match jobs
            # Assuming jobs with match_score >= threshold and status == 'new' need notification.
            # We fetch the exact jobs that are newly scored.
            async with async_session_factory() as session:
                threshold = getattr(settings, 'MATCH_THRESHOLD', 70)
                stmt = select(Job).where(
                    Job.match_score >= threshold,
                    Job.status == 'new'
                )
                result = await session.execute(stmt)
                high_match_jobs = list(result.scalars().all())

            # 4. Notify
            if high_match_jobs:
                notified_count = await notifier_service.notify_high_match_jobs(high_match_jobs)
                logger.info(f"Sent {notified_count} notifications for high-match jobs.")
            else:
                logger.info("No high-match jobs found to notify.")
                
        except Exception as e:
            logger.exception(f"Error occurred during scrape pipeline execution: {e}")

scheduler_service = SchedulerService()
