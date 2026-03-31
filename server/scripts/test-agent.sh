#!/usr/bin/env bash
set -euo pipefail

if [ -z "${DASHSCOPE_API_KEY:-}" ]; then
    echo "ERROR: DASHSCOPE_API_KEY not set. Agent tests require LLM access."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$(dirname "$PROJECT_ROOT")/docker-compose.test.yml"
COMPOSE_PROJECT="chronos-test"

echo "Starting test infrastructure (including target databases)..."
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" up -d --wait

echo "Infrastructure ready. Running agent integration tests..."
cd "$PROJECT_ROOT"
uv run pytest tests/agent/ -x -v --timeout=300 "$@"
TEST_EXIT=$?

echo "Tearing down test infrastructure..."
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" down -v

exit $TEST_EXIT
