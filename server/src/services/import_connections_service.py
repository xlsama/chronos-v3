import json
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ExtractedConnections, ExtractedServer, ExtractedService
from src.db.models import ProjectDocument, Server, Service
from src.env import get_settings
from src.lib.logger import get_logger

log = get_logger()

SYSTEM_PROMPT = """\
你是一个运维信息提取专家。你的任务是从项目文档中提取所有提及的服务（数据库、中间件等）和服务器（SSH）信息。

请严格按照以下 JSON 格式输出：

{
  "services": [
    {
      "name": "服务名称",
      "description": "简要描述",
      "service_type": "类型",
      "host": "主机地址",
      "port": 端口号,
      "password": "密码",
      "config": {"username": "用户名", "database": "数据库名"}
    }
  ],
  "servers": [
    {
      "name": "服务器名称",
      "description": "简要描述",
      "host": "主机地址",
      "port": 22,
      "username": "root",
      "password": "密码"
    }
  ]
}

规则：
1. service_type 只能是以下值之一：mysql, postgresql, redis, prometheus, mongodb, elasticsearch, doris, starrocks, jenkins, kettle, hive, kubernetes, docker
2. 如果文档中未明确提及端口号，请根据服务类型推断默认端口（如 MySQL=3306, PostgreSQL=5432, Redis=6379, MongoDB=27017, Elasticsearch=9200, Prometheus=9090, Doris=9030, StarRocks=9030, Jenkins=8080, Kettle=8181, Hive=10000, Docker=2376）
3. 服务器端口默认为 22，用户名默认为 root
4. 不要凭空捏造文档中未提及的连接信息
5. 如果某个字段在文档中无法确定，设为 null
6. config 对象中可包含 username（数据库用户名）、database（数据库名）、path（API 路径）、use_tls（是否启用 TLS）等附加信息
9. password 字段：services 和 servers 均适用，如果文档中明确提及了密码则提取，否则设为 null
7. name 应该是有意义的标识名，如果文档中有明确名称就用文档中的，否则根据用途和地址生成
8. 如果文档中没有任何服务或服务器信息，对应数组返回空 []
"""


def _build_import_warnings(
    services: list[ExtractedService],
    servers: list[ExtractedServer],
) -> list[str]:
    warnings: list[str] = []
    if not services and not servers:
        warnings.append("未从文档中识别到任何服务或服务器连接信息。")
    elif services and not servers:
        warnings.append(
            "仅识别到服务连接，未识别到可 SSH 的服务器资产。"
            "故障 Agent 可以判断依赖是否可连，但无法通过 SSH 执行重启或日志排查。"
        )
    return warnings


class ImportConnectionsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        s = get_settings()
        self.client = AsyncOpenAI(api_key=s.dashscope_api_key, base_url=s.llm_base_url)
        self.model = s.mini_model

    async def extract(
        self,
        project_id: uuid.UUID,
        disconnect_check: Callable[[], Coroutine[Any, Any, bool]] | None = None,
    ) -> ExtractedConnections:
        pid = str(project_id)

        # ── 阶段 1: 加载文档 ──
        log.info("=== 导入连接: 开始 ===", project_id=pid)
        log.info("[1/4] 正在加载项目文档...", project_id=pid)

        result = await self.session.execute(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.created_at.asc())
        )
        documents = list(result.scalars().all())
        log.info(
            "[1/4] 查询到文档",
            project_id=pid,
            total_docs=len(documents),
        )

        # Filter out memory_config and empty documents
        docs_with_content = [
            doc
            for doc in documents
            if doc.doc_type != "memory_config" and doc.content and doc.content.strip()
        ]

        log.info(
            "[1/4] 过滤后有效文档",
            project_id=pid,
            valid_docs=len(docs_with_content),
            filtered_out=len(documents) - len(docs_with_content),
        )

        if not docs_with_content:
            log.warning("[1/4] 没有有效文档，跳过提取", project_id=pid)
            return ExtractedConnections(
                services=[],
                servers=[],
                warnings=["未找到可分析的项目文档。"],
            )

        # Log each document details
        total_chars = 0
        for doc in docs_with_content:
            doc_chars = len(doc.content)
            total_chars += doc_chars
            log.info(
                "[1/4] 文档详情",
                project_id=pid,
                filename=doc.filename,
                doc_type=doc.doc_type,
                content_chars=doc_chars,
                status=doc.status,
            )

        log.info(
            "[1/4] 文档加载完成",
            project_id=pid,
            total_docs=len(docs_with_content),
            total_chars=total_chars,
        )

        # ── 阶段 2: 构建 Prompt ──
        log.info("[2/4] 正在构建 Prompt...", project_id=pid)

        doc_sections = []
        for doc in docs_with_content:
            doc_sections.append(f"--- 文档: {doc.filename} ---\n{doc.content}")
        user_prompt = "请从以下项目文档中提取所有服务和服务器连接信息：\n\n" + "\n\n".join(
            doc_sections
        )

        log.info(
            "[2/4] Prompt 构建完成",
            project_id=pid,
            model=self.model,
            system_prompt_chars=len(SYSTEM_PROMPT),
            user_prompt_chars=len(user_prompt),
            total_prompt_chars=len(SYSTEM_PROMPT) + len(user_prompt),
        )

        # ── 阶段 3: 调用 LLM (流式) ──
        log.info(
            "[3/4] 正在调用 LLM...",
            project_id=pid,
            model=self.model,
            temperature=0.1,
            response_format="json_object",
        )

        t0 = time.monotonic()
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            stream=True,
        )

        # Collect streamed chunks
        content_chunks: list[str] = []
        chunk_count = 0
        usage_info = None

        async for chunk in stream:
            chunk_count += 1
            # Check client disconnect every 10 chunks
            if disconnect_check and chunk_count % 10 == 0:
                if await disconnect_check():
                    log.warning(
                        "[3/4] 客户端已断开，终止 LLM 流",
                        project_id=pid,
                        chunks_received=chunk_count,
                    )
                    await stream.close()
                    return ExtractedConnections(services=[], servers=[], warnings=[])
            # Extract content delta
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                content_chunks.append(delta)
            # Capture usage from final chunk
            if hasattr(chunk, "usage") and chunk.usage:
                usage_info = chunk.usage

        elapsed = time.monotonic() - t0
        content = "".join(content_chunks) or "{}"

        log.info(
            "[3/4] LLM 调用完成",
            project_id=pid,
            elapsed=f"{elapsed:.2f}s",
            chunks_received=chunk_count,
            response_chars=len(content),
        )

        # Log token usage if available
        if usage_info:
            log.info(
                "[3/4] Token 用量",
                project_id=pid,
                prompt_tokens=getattr(usage_info, "prompt_tokens", None),
                completion_tokens=getattr(usage_info, "completion_tokens", None),
                total_tokens=getattr(usage_info, "total_tokens", None),
            )

        # Log full raw LLM response
        log.info(
            "[3/4] LLM 原始输出",
            project_id=pid,
            raw_response=content,
        )

        # ── 阶段 4: 解析结果 ──
        log.info("[4/4] 正在解析 LLM 输出...", project_id=pid)

        try:
            data = json.loads(content)
            log.info("[4/4] JSON 解析成功", project_id=pid)
        except json.JSONDecodeError as e:
            log.error(
                "[4/4] JSON 解析失败",
                project_id=pid,
                error=str(e),
                content_preview=content[:500],
            )
            return ExtractedConnections(
                services=[],
                servers=[],
                warnings=["LLM 输出解析失败，未能提取连接信息。"],
            )

        # Parse services
        raw_services = data.get("services", [])
        services: list[ExtractedService] = []
        for i, svc in enumerate(raw_services):
            if not isinstance(svc, dict) or not svc.get("name"):
                log.warning("[4/4] 跳过无效 service 条目", index=i, data=svc)
                continue
            extracted = ExtractedService(**svc)
            services.append(extracted)
            log.info(
                "[4/4] 提取到服务",
                project_id=pid,
                index=i,
                name=extracted.name,
                service_type=extracted.service_type,
                host=extracted.host,
                port=extracted.port,
                config=extracted.config,
                description=extracted.description,
            )

        # Parse servers
        raw_servers = data.get("servers", [])
        servers: list[ExtractedServer] = []
        for i, srv in enumerate(raw_servers):
            if not isinstance(srv, dict) or not srv.get("name"):
                log.warning("[4/4] 跳过无效 server 条目", index=i, data=srv)
                continue
            extracted = ExtractedServer(**srv)
            servers.append(extracted)
            log.info(
                "[4/4] 提取到服务器",
                project_id=pid,
                index=i,
                name=extracted.name,
                host=extracted.host,
                port=extracted.port,
                username=extracted.username,
                description=extracted.description,
            )

        # ── 标记已存在的连接 ──
        await self._mark_existing(services, servers)
        existing_svc = sum(1 for s in services if s.existing_name)
        existing_srv = sum(1 for s in servers if s.existing_name)
        if existing_svc or existing_srv:
            log.info(
                "[4/4] 检测到已有重复项",
                project_id=pid,
                existing_services=existing_svc,
                existing_servers=existing_srv,
            )

        warnings = _build_import_warnings(services, servers)
        for warning in warnings:
            log.warning("[4/4] 导入提示", project_id=pid, warning=warning)

        log.info(
            "=== 导入连接: 完成 ===",
            project_id=pid,
            total_services=len(services),
            total_servers=len(servers),
            warnings=len(warnings),
            total_elapsed=f"{time.monotonic() - t0:.2f}s",
        )
        return ExtractedConnections(
            services=services,
            servers=servers,
            warnings=warnings,
        )

    async def _mark_existing(
        self,
        services: list[ExtractedService],
        servers: list[ExtractedServer],
    ) -> None:
        """将已存在于数据库中的连接标记 existing_name（按 host+port+type 匹配）。"""
        # 服务: (host, port, service_type) -> name
        result = await self.session.execute(select(Service))
        svc_lookup: dict[tuple[str, int, str], str] = {}
        for s in result.scalars().all():
            key = (s.host.lower(), s.port, s.service_type.lower())
            svc_lookup[key] = s.name

        for svc in services:
            if svc.host and svc.port and svc.service_type:
                key = (svc.host.lower(), svc.port, svc.service_type.lower())
                if key in svc_lookup:
                    svc.existing_name = svc_lookup[key]

        # 服务器: (host, port) -> name
        result = await self.session.execute(select(Server))
        srv_lookup: dict[tuple[str, int], str] = {}
        for s in result.scalars().all():
            key = (s.host.lower(), s.port)
            srv_lookup[key] = s.name

        for srv in servers:
            port = srv.port if srv.port is not None else 22
            if srv.host:
                key = (srv.host.lower(), port)
                if key in srv_lookup:
                    srv.existing_name = srv_lookup[key]
