# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chronos V3 是一个运维自动化系统，基于 LangGraph 构建 Ops Agent，支持事件响应、人工审批、多服务连接器集成。
- 后端：FastAPI + LangGraph + SQLAlchemy 2.x (async) + PostgreSQL (pgvector)
- 前端：React 19 + TanStack Router/Query/Form + Tailwind CSS 4 + shadcn/ui
- AI：Qwen (DashScope) — qwen3.5-plus / qwen3.5-flash / text-embedding-v4

## Commands

### Server (Python, uv + poethepoet)
```bash
cd server && poe dev          # uvicorn --reload :8000
cd server && poe lint         # ruff check src/
cd server && poe format       # ruff format src/
cd server && poe migrate      # alembic upgrade head
cd server && poe migrate:new  # alembic revision --autogenerate
```

### Web (TypeScript, pnpm)
```bash
cd web && pnpm dev            # vite dev
cd web && pnpm build          # tsc + vite build
cd web && pnpm lint           # eslint
```

### Test (Python, pytest)
```bash
cd test && uv run pytest                    # all tests
cd test && uv run pytest test_xxx.py        # single file
cd test && uv run pytest -k 'test_name'     # single test
```

### Infrastructure
```bash
docker compose up -d   # PostgreSQL 17 (pgvector) + Redis 7
```

## Development Practices

- **TDD**：API 开发先写测试用例，再写实现
- **SSH 必须用 asyncssh**，禁止用 paramiko（全 async 架构，需要真正并发）
- 后端代码风格：ruff，line-length=100
- 前端代码风格：ESLint + TypeScript strict mode

## Architecture Notes

- LangGraph 图在 `server/src/ops_agent/graph.py`，中断点：human_approval、ask_human、confirm_resolution
- 服务连接器在 `server/src/ops_agent/tools/service_connectors/`，支持 PG、MySQL、MongoDB、ES、K8s、Jenkins 等
- 数据库迁移用 Alembic autogenerate，修改 model 后跑 `poe migrate:new`
- 环境变量配置见 `server/.env.example`
