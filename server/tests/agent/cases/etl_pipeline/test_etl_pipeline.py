"""Agent integration test: ETL pipeline data mismatch troubleshooting.

Tests the full flow:
1. Register 3 MySQL services (source, staging, target)
2. Create project + upload KB document describing the ETL architecture
3. Wait for document indexing
4. Import connections from KB documents (LLM extracts MySQL info)
5. Run correct ETL -> data consistent
6. Run buggy ETL -> data mismatch introduced
7. Create incident: "downstream counts don't match"
8. Agent investigates across all 3 databases
9. Verify agent reaches terminal state with findings

Requires:
- docker-compose.dev.yml running (PG + Redis)
- docker-compose.agent.yml + docker-compose.etl.yml running (target databases)
- DASHSCOPE_API_KEY environment variable set
"""

import asyncio
import logging
import warnings
from pathlib import Path

import pytest

from tests.agent.conftest import poll_for_terminal_state, poll_incident_status
from tests.factories import make_project_payload, make_service_payload

from tests.agent.cases.etl_pipeline.conftest import (
    SOURCE_DB_CONFIG,
    STAGING_DB_CONFIG,
    TARGET_DB_CONFIG,
)
from tests.agent.cases.etl_pipeline.etl_scripts.etl_buggy import run_buggy_etl
from tests.agent.cases.etl_pipeline.etl_scripts.etl_correct import run_correct_etl

pytestmark = [pytest.mark.agent, pytest.mark.timeout(600)]

log = logging.getLogger(__name__)

KB_DOC_PATH = Path(__file__).parent / "knowledge_docs" / "etl_architecture.md"

# 事件提示词
INCIDENT_DESCRIPTION = (
    "ETL 数据管道异常告警：目标库 daily_sales_summary 的聚合总订单数与"
    "清洗库 clean_orders 的总记录数不匹配。"
    "target_db 上 SELECT SUM(order_count) FROM daily_sales_summary 结果为 180，"
    "但 staging_db 上 SELECT COUNT(*) FROM clean_orders 结果为 200。"
    "差异 20 条记录，请排查是哪个 ETL 环节出了问题。"
    "相关服务: mysql-etl-source, mysql-etl-staging, mysql-etl-target"
)


async def _wait_for_document_indexed(
    client, project_id: str, timeout: float = 60.0
) -> list[dict]:
    """Poll until all non-agents_config documents in the project are indexed."""
    deadline = asyncio.get_event_loop().time() + timeout
    docs = []
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/projects/{project_id}/documents")
        docs = resp.json()
        user_docs = [d for d in docs if d["doc_type"] != "agents_config"]
        if user_docs and all(d["status"] in ("indexed", "index_failed") for d in user_docs):
            return docs
        await asyncio.sleep(2.0)
    raise TimeoutError(
        f"Documents not indexed within {timeout}s. "
        f"Statuses: {[(d['filename'], d['status']) for d in docs]}"
    )


async def _poll_for_terminal_state_with_approvals(
    client, incident_id: str, timeout: float = 300.0, interval: float = 3.0
) -> dict:
    """Extended poll that also auto-approves write operations."""
    terminal_statuses = {"resolved", "stopped", "error"}
    deadline = asyncio.get_event_loop().time() + timeout
    last_data: dict = {}
    handled_event_ids: set[str] = set()

    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/incidents/{incident_id}")
        last_data = resp.json()
        if last_data["status"] in terminal_statuses:
            return last_data

        events_resp = await client.get(f"/api/incidents/{incident_id}/events")
        events = events_resp.json()

        for evt in events:
            evt_id = evt.get("event_id", "")
            if evt_id in handled_event_ids:
                continue

            if evt["event_type"] == "confirm_resolution_required":
                handled_event_ids.add(evt_id)
                await client.post(f"/api/incidents/{incident_id}/confirm-resolution")
                log.info("[poll] Auto-confirmed resolution")
                await asyncio.sleep(1)

            elif evt["event_type"] == "ask_human" and last_data["status"] == "investigating":
                handled_event_ids.add(evt_id)
                await client.post(
                    f"/api/incidents/{incident_id}/messages",
                    json={"content": "请继续自动排查，不需要额外信息。"},
                )
                log.info("[poll] Auto-replied to ask_human")
                await asyncio.sleep(1)

            elif evt["event_type"] == "approval_required":
                handled_event_ids.add(evt_id)
                approval_id = evt.get("data", {}).get("approval_id")
                if approval_id:
                    await client.post(
                        f"/api/approvals/{approval_id}/decide",
                        json={"decision": "approved", "decided_by": "test-auto"},
                    )
                    log.info(f"[poll] Auto-approved {approval_id}")
                    await asyncio.sleep(1)

        await asyncio.sleep(interval)

    raise TimeoutError(
        f"Incident {incident_id} did not reach terminal state within {timeout}s. "
        f"Last status: {last_data.get('status', 'unknown')}"
    )


class TestETLPipelineTroubleshooting:
    """Full ETL pipeline troubleshooting scenario."""

    async def test_etl_pipeline_investigation(self, agent_client, etl_databases):
        client = agent_client

        # ── Phase 1: 注册 3 个 MySQL 服务 ──
        log.info("=== Phase 1: Registering MySQL services ===")

        service_configs = [
            (
                "mysql-etl-source",
                {
                    "host": "localhost",
                    "port": 13307,
                    "password": "sourcepass",
                    "config": {"database": "source_db", "username": "etl_user"},
                },
            ),
            (
                "mysql-etl-staging",
                {
                    "host": "localhost",
                    "port": 13308,
                    "password": "stagingpass",
                    "config": {"database": "staging_db", "username": "etl_user"},
                },
            ),
            (
                "mysql-etl-target",
                {
                    "host": "localhost",
                    "port": 13309,
                    "password": "targetpass",
                    "config": {"database": "target_db", "username": "etl_user"},
                },
            ),
        ]

        services = {}
        for name, config in service_configs:
            svc_resp = await client.post(
                "/api/services",
                json=make_service_payload(name=name, service_type="mysql", **config),
            )
            assert svc_resp.status_code == 200, (
                f"Failed to create service {name}: {svc_resp.text}"
            )
            services[name] = svc_resp.json()
            log.info(f"Registered service: {name} (id={services[name]['id']})")

        # ── Phase 2: 创建项目 + 上传 KB 文档 ──
        log.info("=== Phase 2: Creating project and uploading KB document ===")

        proj_resp = await client.post(
            "/api/projects",
            json=make_project_payload(
                name="ETL Pipeline Project",
                slug="etl-pipeline-test",
            ),
        )
        assert proj_resp.status_code == 200
        project = proj_resp.json()
        project_id = project["id"]
        log.info(f"Created project: {project['name']} (id={project_id})")

        # 上传架构文档
        kb_content = KB_DOC_PATH.read_text(encoding="utf-8")
        doc_resp = await client.post(
            f"/api/projects/{project_id}/documents",
            json={
                "filename": "etl_architecture.md",
                "content": kb_content,
                "doc_type": "markdown",
            },
        )
        assert doc_resp.status_code == 200
        doc = doc_resp.json()
        log.info(f"Uploaded document: {doc['filename']} (id={doc['id']})")

        # 等待文档索引完成
        indexed_docs = await _wait_for_document_indexed(client, project_id, timeout=60)
        etl_doc = next(
            (d for d in indexed_docs if d["filename"] == "etl_architecture.md"), None
        )
        assert etl_doc is not None, "ETL architecture doc not found"
        assert etl_doc["status"] == "indexed", (
            f"Doc indexing failed, status: {etl_doc['status']}"
        )
        log.info("Document indexed successfully")

        # ── Phase 3: 从文档导入连接信息 ──
        log.info("=== Phase 3: Importing connections from documents ===")

        import_resp = await client.post(
            f"/api/projects/{project_id}/import-connections"
        )
        assert import_resp.status_code == 200
        extracted = import_resp.json()

        extracted_services = extracted.get("services", [])
        log.info(
            f"Extracted {len(extracted_services)} services: "
            f"{[s['name'] for s in extracted_services]}"
        )

        # 验证 LLM 提取出了至少 3 个 MySQL 服务
        mysql_services = [
            s for s in extracted_services if s.get("service_type") == "mysql"
        ]
        assert len(mysql_services) >= 3, (
            f"Expected >= 3 MySQL services extracted, got {len(mysql_services)}: "
            f"{[s['name'] for s in mysql_services]}"
        )

        # ── Phase 4: 运行正确 ETL ──
        log.info("=== Phase 4: Running correct ETL ===")

        correct_stats = await run_correct_etl(
            SOURCE_DB_CONFIG, STAGING_DB_CONFIG, TARGET_DB_CONFIG
        )
        assert correct_stats["source_completed"] == 180, (
            f"Expected 180 completed orders, got {correct_stats['source_completed']}"
        )
        assert correct_stats["staging_loaded"] == 180, (
            f"Expected 180 staging rows, got {correct_stats['staging_loaded']}"
        )
        log.info(f"Correct ETL done: {correct_stats}")

        # ── Phase 5: 运行 buggy ETL → 制造数据不一致 ──
        log.info("=== Phase 5: Running buggy ETL (injecting data mismatch) ===")

        buggy_stats = await run_buggy_etl(
            SOURCE_DB_CONFIG, STAGING_DB_CONFIG, TARGET_DB_CONFIG
        )
        assert buggy_stats["source_extracted"] == 200, (
            f"Expected 200 extracted, got {buggy_stats['source_extracted']}"
        )
        assert buggy_stats["staging_loaded"] == 200, (
            f"Expected 200 staging rows (buggy), got {buggy_stats['staging_loaded']}"
        )
        log.info(f"Buggy ETL done: {buggy_stats}")
        log.info("Data mismatch injected: staging=200, target SUM(order_count)=180")

        # ── Phase 6: 创建事件 ──
        log.info("=== Phase 6: Creating incident ===")

        incident_resp = await client.post(
            "/api/incidents",
            json={
                "description": INCIDENT_DESCRIPTION,
                "severity": "P2",
            },
        )
        assert incident_resp.status_code == 200
        incident = incident_resp.json()
        incident_id = incident["id"]
        assert incident["status"] == "open"
        log.info(f"Created incident: {incident_id}")

        # ── Phase 7: 等待 Agent 进入 investigating 状态 ──
        log.info("=== Phase 7: Waiting for agent to start investigating ===")

        await poll_incident_status(
            client, incident_id, {"investigating"}, timeout=30
        )
        log.info("Agent is investigating")

        # ── Phase 8: 等待 Agent 达到终态 ──
        log.info("=== Phase 8: Waiting for terminal state ===")

        final = await _poll_for_terminal_state_with_approvals(
            client, incident_id, timeout=300
        )
        log.info(f"Agent reached terminal state: {final['status']}")

        # ── Phase 9: 验证结果 ──
        log.info("=== Phase 9: Verifying results ===")

        assert final["status"] in ("resolved", "stopped", "error"), (
            f"Unexpected final status: {final['status']}"
        )

        # 验证产生了消息
        msgs_resp = await client.get(f"/api/incidents/{incident_id}/messages")
        assert msgs_resp.status_code == 200
        messages = msgs_resp.json()
        assert len(messages) > 0, "Agent should have generated at least one message"
        log.info(f"Agent generated {len(messages)} messages")

        # 验证 thread_id 已设置（Agent 实际运行了）
        detail_resp = await client.get(f"/api/incidents/{incident_id}")
        detail = detail_resp.json()
        assert detail["thread_id"] is not None, "Agent should have set thread_id"

        # 验证 Agent 使用了 service_exec 工具查询数据库
        events_resp = await client.get(f"/api/incidents/{incident_id}/events")
        events = events_resp.json()

        tool_use_events = [e for e in events if e["event_type"] == "tool_use"]
        log.info(
            f"Tool use events: "
            f"{[e.get('data', {}).get('name', '?') for e in tool_use_events]}"
        )
        assert len(tool_use_events) > 0, "Agent should have used tools"

        service_exec_calls = [
            e
            for e in tool_use_events
            if e.get("data", {}).get("name") == "service_exec"
        ]
        assert len(service_exec_calls) > 0, (
            "Agent should have called service_exec to query databases"
        )
        log.info(f"Agent made {len(service_exec_calls)} service_exec calls")

        # 软断言：Agent 输出是否提及关键数字/关键词
        text_events = [
            e
            for e in events
            if e["event_type"]
            in ("thinking", "answer", "sub_agent_reporting", "sub_agent_completed")
        ]
        all_text = " ".join(
            e.get("data", {}).get("content", "")
            or e.get("data", {}).get("report", "")
            or e.get("data", {}).get("summary", "")
            or ""
            for e in text_events
        )

        keywords = ["200", "180", "20", "cancelled", "取消", "过滤", "filter", "status"]
        has_keyword = any(kw in all_text for kw in keywords)
        if not has_keyword:
            warnings.warn(
                "Agent output did not contain expected keywords about the data mismatch "
                "(200/180/cancelled/filter). This may be acceptable if the agent "
                "took a different investigation path.",
                stacklevel=1,
            )
        else:
            log.info("Agent output contains expected keywords about the data mismatch")

        log.info("=== Test completed successfully ===")
