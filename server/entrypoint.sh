#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting server..."
exec uv run uvicorn src.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${UVICORN_WORKERS:-2}"
