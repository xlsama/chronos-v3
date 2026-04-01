import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.env import get_settings
from src.lib.logger import get_logger

log = get_logger(component="cron")

_scheduler: AsyncIOScheduler | None = None


async def _safe_run(coro, task_name: str) -> str:
    """运行协程，捕获异常以隔离失败。"""
    try:
        await coro
        return f"{task_name}: ok"
    except Exception:
        log.error(f"Evolution sub-task failed: {task_name}", exc_info=True)
        return f"{task_name}: error"


async def _run_evolution_jobs() -> None:
    """获取共享数据，并行运行 skill evolution 和 AGENTS.md batch update。"""
    from src.services.cron.agents_md_evolution_job import run_agents_md_evolution_job
    from src.services.cron.shared import fetch_recent_data
    from src.services.cron.skill_evolution_job import run_skill_evolution_job

    log.info("=== Evolution Jobs Started ===")

    try:
        incidents, agents_docs = await fetch_recent_data()

        if not incidents:
            log.info("No recent incidents, skipping all evolution jobs")
            return

        results = await asyncio.gather(
            _safe_run(
                run_skill_evolution_job(incidents, agents_docs),
                "skill_evolution",
            ),
            _safe_run(
                run_agents_md_evolution_job(incidents, agents_docs),
                "agents_md_evolution",
            ),
        )
        log.info("=== Evolution Jobs Completed ===", results=results)
    except Exception:
        log.error("Evolution Jobs failed at data fetch stage", exc_info=True)


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _run_evolution_jobs,
        trigger=IntervalTrigger(hours=settings.skill_evolution_interval),
        id="evolution_jobs",
        name="Evolution Jobs (Skill + AGENTS.md)",
        misfire_grace_time=3600,
        max_instances=1,
    )
    _scheduler.start()
    log.info(
        "Cron scheduler started",
        jobs=len(_scheduler.get_jobs()),
        evolution_interval=f"{settings.skill_evolution_interval}h",
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        log.info("Cron scheduler stopped")
        _scheduler = None
