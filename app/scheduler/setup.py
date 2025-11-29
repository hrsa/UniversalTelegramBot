from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import timezone

from app.scheduler import jobs

scheduler = AsyncIOScheduler()


def setup_scheduler():
    scheduler.add_job(
        jobs.notify_and_kick_members_without_greetings,
        CronTrigger(hour=19, minute=00, timezone=timezone.utc),
        misfire_grace_time=180
    )

    scheduler.start()
    return scheduler
