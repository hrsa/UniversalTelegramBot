from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import timezone

from apscheduler.triggers.interval import IntervalTrigger

from app.scheduler import jobs

scheduler = AsyncIOScheduler(job_defaults={"misfire_grace_time": None})


def setup_scheduler():
    scheduler.add_job(
        jobs.notify_and_kick_members_without_greetings,
        CronTrigger(hour=19, minute=00, timezone=timezone.utc)
    )

    scheduler.add_job(
        jobs.get_group_admins,
        CronTrigger(hour=1, minute=00, timezone=timezone.utc)
    )

    scheduler.add_job(
        jobs.check_expired_messages,
        CronTrigger(hour=0, minute=0, timezone=timezone.utc)
    )

    scheduler.add_job(
        jobs.invalidate_old_pending_payments,
        IntervalTrigger(minutes=1, timezone=timezone.utc)
    )

    scheduler.add_job(
        jobs.activate_waiting_payments,
        IntervalTrigger(minutes=1, timezone=timezone.utc)
    )

    scheduler.start()
    return scheduler
