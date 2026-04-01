#!/usr/bin/env bash
set -euo pipefail

# Requires: docker compose -f docker-compose.dev.yml up -d (PG + Redis)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"
uv run pytest tests/ -x -v --ignore=tests/agent "$@"
