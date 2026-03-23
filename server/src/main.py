import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import AsyncConnection

from src.db.connection import get_session_factory
from src.ops_agent.event_publisher import EventPublisher
from src.api.approvals import router as approvals_router
from src.api.attachments import router as attachments_router
from src.api.documents import router as documents_router
from src.api.incidents import router as incidents_router
from src.api.servers import router as servers_router
from src.api.projects import router as projects_router
from src.api.asr import router as asr_router
from src.env import get_settings
from src.lib.errors import AppError
from src.lib.logger import get_logger
from src.lib.redis import get_redis
from src.services.agent_runner import AgentRunner

log = get_logger()


def _run_migrations():
    import subprocess

    subprocess.run(["alembic", "upgrade", "head"], check=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Chronos Ops Agent")

    # Run database migrations
    log.info("Running database migrations...")
    _run_migrations()
    log.info("Database migrations completed")

    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)

    # 创建运行时数据目录
    from src.lib.paths import skills_dir, incident_history_dir, knowledge_dir

    for d in [skills_dir(), incident_history_dir(), knowledge_dir()]:
        d.mkdir(parents=True, exist_ok=True)

    # 从 seeds/ 复制内置 skills 到 data/skills/
    from src.lib.seeder import seed_skills

    await seed_skills(get_session_factory())

    for warning in settings.validate_production_secrets():
        log.warning(warning)

    # Initialize LangGraph checkpointer with PostgreSQL
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    conn = await AsyncConnection.connect(settings.langgraph_checkpoint_dsn, autocommit=True)
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()

    # Initialize EventPublisher + AgentRunner
    publisher = EventPublisher(redis=get_redis(), session_factory=get_session_factory())
    app.state.agent_runner = AgentRunner(publisher=publisher, checkpointer=checkpointer, redis=get_redis())

    log.info("Agent runner initialized")

    yield

    await conn.close()
    log.info("Shutting down Chronos Ops Agent")


app = FastAPI(
    title="Chronos Ops Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health")
async def health():
    return {"status": "ok"}


from src.api.incident_history import router as incident_history_router
from src.api.notification_settings import router as notification_settings_router
from src.api.skills import router as skills_router
from src.api.services import router as services_router
from src.api.versions import router as versions_router

app.include_router(servers_router)
app.include_router(incidents_router)
app.include_router(approvals_router)
app.include_router(attachments_router)
app.include_router(projects_router)
app.include_router(documents_router)
app.include_router(asr_router)
app.include_router(incident_history_router)
app.include_router(notification_settings_router)
app.include_router(skills_router)
app.include_router(services_router)
app.include_router(versions_router)
