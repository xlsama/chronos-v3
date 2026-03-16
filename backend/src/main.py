import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg import AsyncConnection

from src.ops_agent.event_publisher import EventPublisher
from src.api.approvals import router as approvals_router
from src.api.attachments import router as attachments_router
from src.api.documents import router as documents_router
from src.api.incidents import router as incidents_router
from src.api.connections import router as connections_router
from src.api.projects import router as projects_router
from src.api.asr import router as asr_router
from src.api.monitoring_sources import router as monitoring_sources_router
from src.api.services import router as services_router
from src.api.service_dependencies import router as service_dependencies_router
from src.api.service_bindings import router as service_bindings_router
from src.config import get_settings
from src.lib.errors import AppError
from src.lib.logger import logger
from src.lib.redis import get_redis
from src.services.agent_runner import AgentRunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Chronos Ops Agent")

    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)

    for warning in settings.validate_production_secrets():
        logger.warning(warning)

    # Initialize LangGraph checkpointer with PostgreSQL
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    conn = await AsyncConnection.connect(settings.langgraph_checkpoint_dsn, autocommit=True)
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()

    # Initialize EventPublisher + AgentRunner
    publisher = EventPublisher(redis=get_redis())
    app.state.agent_runner = AgentRunner(publisher=publisher, checkpointer=checkpointer)

    logger.info("Agent runner initialized")

    yield

    await conn.close()
    logger.info("Shutting down Chronos Ops Agent")


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


app.include_router(connections_router)
app.include_router(incidents_router)
app.include_router(approvals_router)
app.include_router(attachments_router)
app.include_router(projects_router)
app.include_router(documents_router)
app.include_router(services_router)
app.include_router(service_dependencies_router)
app.include_router(service_bindings_router)
app.include_router(monitoring_sources_router)
app.include_router(asr_router)
