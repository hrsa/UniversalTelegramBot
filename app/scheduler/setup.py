from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import timezone

from app.scheduler import jobs

scheduler = AsyncIOScheduler()


def setup_scheduler():
    scheduler.add_job(
        jobs.find_members_without_greetings_to_notify,
        CronTrigger(hour=19, minute=00, timezone=timezone.utc)
    )

    scheduler.start()
    return scheduler
