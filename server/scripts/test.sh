#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$(dirname "$PROJECT_ROOT")/docker-compose.test.yml"
COMPOSE_PROJECT="chronos-test"

echo "Starting test infrastructure..."
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" up -d --wait

echo "Infrastructure ready. Running tests..."
cd "$PROJECT_ROOT"
uv run pytest tests/ -x -v --ignore=tests/agent "$@"
TEST_EXIT=$?

echo "Tearing down test infrastructure..."
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" down -v

exit $TEST_EXIT
