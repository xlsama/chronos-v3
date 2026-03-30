from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.env import get_settings
from src.lib.logger import get_logger
from src.services.cron.skill_evolution_job import run_skill_evolution_job

log = get_logger(component="cron")

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_skill_evolution_job,
        trigger=IntervalTrigger(hours=settings.skill_evolution_interval),
        id="skill_evolution",
        name="Skill Evolution",
        misfire_grace_time=3600,
        max_instances=1,
    )
    _scheduler.start()
    log.info(
        "Cron scheduler started",
        jobs=len(_scheduler.get_jobs()),
        skill_evolution_interval=f"{settings.skill_evolution_interval}h",
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        log.info("Cron scheduler stopped")
        _scheduler = None
