import logging
import apprise
from sqlalchemy import select

from app.models import Job, AppConfig
from app.config import settings
from app.database import async_session_factory

logger = logging.getLogger(__name__)

class NotifierService:
    async def notify_high_match_jobs(self, jobs: list[Job]) -> int:
        """Send notifications for jobs exceeding match threshold. Returns count sent."""
        notified_count = 0
        threshold = getattr(settings, 'MATCH_THRESHOLD', 70)

        for job in jobs:
            score = job.match_score or 0
            if score >= threshold:
                title = f"New Job Match: {job.title} at {job.company}"
                body = (
                    f"🎯 {job.title} at {job.company}\n"
                    f"Score: {score}/100\n"
                    f"{job.match_summary or 'No summary'}\n"
                    f"📍 {job.location or 'Unknown'}\n"
                    f"🔗 {job.url}"
                )
                success = await self.send_notification(title=title, body=body)
                if success:
                    notified_count += 1
                else:
                    logger.error(f"Failed to send notification for job: {job.id}")
                    
        return notified_count

    async def send_notification(self, title: str, body: str) -> bool:
        """Send a notification via all configured Apprise URLs."""
        apobj = apprise.Apprise()
        
        # Add URLs from environment/settings
        env_urls = settings.get_apprise_urls()
        for url in env_urls:
            apobj.add(url)
            
        # Add URLs from database config
        async with async_session_factory() as session:
            stmt = select(AppConfig).where(AppConfig.key == 'apprise_urls')
            result = await session.execute(stmt)
            config = result.scalar_one_or_none()
            if config and config.value:
                # Handle both newline and comma separated URLs
                raw = config.value.replace('\n', ',')
                db_urls = [u.strip() for u in raw.split(',') if u.strip()]
                for url in db_urls:
                    apobj.add(url)

        if len(apobj) == 0:
            logger.warning("No Apprise URLs configured. Skipping notification.")
            return False

        try:
            success = await apobj.async_notify(
                title=title,
                body=body,
                notify_type=apprise.NotifyType.INFO,
                body_format=apprise.NotifyFormat.MARKDOWN
            )
            return success
        except Exception as e:
            logger.exception(f"Exception while sending notification: {e}")
            return False

    async def send_test_notification(self) -> bool:
        """Send a test notification to verify configuration."""
        title = "JobScout Test Notification"
        body = (
            "🎯 Test Job at Test Company\n"
            "Score: 100/100\n"
            "This is a test notification from JobScout to verify your configuration.\n"
            "📍 Remote\n"
            "🔗 https://example.com"
        )
        return await self.send_notification(title=title, body=body)

notifier_service = NotifierService()
