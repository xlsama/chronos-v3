from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.approvals import router as approvals_router
from src.api.incidents import router as incidents_router
from src.api.infrastructures import router as infrastructures_router
from src.lib.errors import AppError
from src.lib.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Chronos Ops Agent")
    yield
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


app.include_router(infrastructures_router)
app.include_router(incidents_router)
app.include_router(approvals_router)
