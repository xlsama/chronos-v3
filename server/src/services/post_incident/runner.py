from src.lib.logger import logger
from src.services.post_incident.agents_md_task import auto_update_agents_md
from src.services.post_incident.history_task import auto_save_history


async def run_post_incident_tasks(
    incident_id: str,
    summary_md: str,
    messages: list,
    description: str,
    project_id: str,
) -> None:
    """顺序执行所有事件后任务。从 AgentRunner._post_run() 调用。"""
    sid = incident_id[:8]

    # Task 1: Auto-save incident history
    try:
        await auto_save_history(incident_id, summary_md)
    except Exception as e:
        logger.error(f"[{sid}] [post_incident] Auto-save history failed: {e}")

    # Task 2: Auto-update AGENTS.md
    try:
        result = await auto_update_agents_md(
            incident_id=incident_id,
            summary_md=summary_md,
            messages=messages,
            description=description,
        )
        logger.info(f"[{sid}] [post_incident] AGENTS.md update result: {result}")
    except Exception as e:
        logger.error(f"[{sid}] [post_incident] AGENTS.md update failed: {e}")
