from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.config import settings
from app.database import async_session_factory
from app.models import Job, ScrapeTarget, ScrapeRun

from app.services.scraper.proxy import ProxyManager
from app.services.scraper.stealth import launch_stealth_browser, random_delay, human_like_scroll
from app.services.scraper.captcha import detect_captcha, solve_captcha, inject_captcha_solution

from app.services.scraper.parsers.greenhouse import GreenhouseParser
from app.services.scraper.parsers.lever import LeverParser
from app.services.scraper.parsers.workday import WorkdayParser
from app.services.scraper.parsers.generic import GenericParser

logger = logging.getLogger(__name__)

class ScrapeOrchestrator:
    """Main scraping orchestrator for JobScout."""
    
    def __init__(self):
        self.proxy_manager = ProxyManager(settings.get_proxy_list())
        
        self.parsers = {
            "greenhouse": GreenhouseParser,
            "lever": LeverParser,
            "workday": WorkdayParser,
            "generic": GenericParser
        }
        
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def run_scrape(self, target_id: int | None = None) -> int:
        """
        Main entry point. Scrapes a specific target or all enabled targets.
        """
        if self._running:
            logger.warning("Scrape run already in progress.")
            return 0
            
        self._running = True
        total_jobs_found = 0
        
        try:
            async with async_session_factory() as session:
                query = select(ScrapeTarget).where(ScrapeTarget.enabled == True)
                if target_id:
                    query = query.where(ScrapeTarget.id == target_id)
                    
                result = await session.execute(query)
                targets = result.scalars().all()
                
                for target in targets:
                    logger.info(f"Starting scrape for target: {target.name}")
                    jobs_found = await self._scrape_target(target, session)
                    total_jobs_found += jobs_found
                    
        except Exception as e:
            logger.error(f"Global scrape run failed: {e}")
        finally:
            self._running = False
            
        return total_jobs_found

    async def _scrape_target(self, target: ScrapeTarget, session: AsyncSession) -> int:
        """Internal method to scrape a single target."""
        new_jobs_found = 0
        run = ScrapeRun(
            target_id=target.id,
            started_at=datetime.now(timezone.utc),
            status="running"
        )
        session.add(run)
        await session.commit()
        
        try:
            parser_class = self.parsers.get(target.ats_type.lower(), GenericParser)
            parser = parser_class()
            
            scraped_jobs = []
            
            # API-based parsers
            if target.ats_type.lower() in ["greenhouse", "lever"]:
                scraped_jobs = await parser.parse(target.url)
                
            # Browser-based parsers
            else:
                playwright, browser, context = await launch_stealth_browser(self.proxy_manager)
                try:
                    page = await context.new_page()
                    
                    # Interception/routing must happen inside parse if needed (e.g. Workday)
                    if target.ats_type.lower() == "generic":
                        custom_selectors = None
                        if target.custom_selectors:
                            try:
                                custom_selectors = json.loads(target.custom_selectors)
                            except json.JSONDecodeError:
                                logger.error(f"Invalid custom_selectors JSON for target {target.id}")
                        
                        # Check FlareSolverr first if configured
                        if settings.CAPTCHA_PROVIDER == "flaresolverr" and settings.FLARESOLVERR_URL:
                            from app.services.scraper.captcha import solve_with_flaresolverr
                            fs_result = await solve_with_flaresolverr(target.url)
                            if fs_result and fs_result.get("cookies"):
                                await context.add_cookies(fs_result["cookies"])
                        
                        await page.goto(target.url)
                        await random_delay()
                        await human_like_scroll(page)
                        
                        # CAPTCHA check
                        captcha_info = await detect_captcha(page)
                        if captcha_info:
                            logger.info(f"CAPTCHA detected on {target.url}. Attempting to solve...")
                            token = await solve_captcha(captcha_info, target.url)
                            if token:
                                await inject_captcha_solution(page, captcha_info, token)
                                await random_delay(2.0, 4.0)
                            else:
                                logger.error("Failed to solve CAPTCHA.")
                                
                        scraped_jobs = await parser.parse(target.url, page=page, custom_selectors=custom_selectors)
                        
                    elif target.ats_type.lower() == "workday":
                        scraped_jobs = await parser.parse(target.url, page=page)
                        
                finally:
                    await context.close()
                    await browser.close()
                    await playwright.stop()

            # Deduplicate and Save
            for job_data in scraped_jobs:
                existing_job = await session.execute(
                    select(Job).where(Job.url == job_data["url"])
                )
                if not existing_job.scalars().first():
                    new_job = Job(
                        url=job_data["url"],
                        company=job_data["company"],
                        title=job_data["title"],
                        description=job_data["description"],
                        location=job_data["location"],
                        source_target_id=target.id,
                        status="new",
                        date_found=datetime.now(timezone.utc)
                    )
                    session.add(new_job)
                    new_jobs_found += 1
                    
            # Update ScrapeRun & Target
            run.status = "success"
            run.jobs_found = new_jobs_found
            run.finished_at = datetime.now(timezone.utc)
            
            target.last_scraped_at = datetime.now(timezone.utc)
            
            await session.commit()
            
        except Exception as e:
            logger.error(f"Failed to scrape target {target.name}: {e}")
            run.status = "failed"
            run.error_message = str(e)
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
            
        return new_jobs_found

scrape_orchestrator = ScrapeOrchestrator()
