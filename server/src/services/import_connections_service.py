import json
import uuid

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import ExtractedConnections, ExtractedServer, ExtractedService
from src.db.models import ProjectDocument
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
      "config": {"username": "用户名", "database": "数据库名"}
    }
  ],
  "servers": [
    {
      "name": "服务器名称",
      "description": "简要描述",
      "host": "主机地址",
      "port": 22,
      "username": "root"
    }
  ]
}

规则：
1. service_type 只能是以下值之一：mysql, postgresql, redis, prometheus, mongodb, elasticsearch, doris, starrocks, jenkins, kettle, hive, kubernetes
2. 如果文档中未明确提及端口号，请根据服务类型推断默认端口（如 MySQL=3306, PostgreSQL=5432, Redis=6379, MongoDB=27017, Elasticsearch=9200, Prometheus=9090, Doris=9030, StarRocks=9030, Jenkins=8080, Kettle=8181, Hive=10000）
3. 服务器端口默认为 22，用户名默认为 root
4. 不要凭空捏造文档中未提及的连接信息
5. 如果某个字段在文档中无法确定，设为 null
6. config 对象中可包含 username（数据库用户名）、database（数据库名）、path（API 路径）、use_tls（是否启用 TLS）等附加信息
7. name 应该是有意义的标识名，如果文档中有明确名称就用文档中的，否则根据用途和地址生成
8. 如果文档中没有任何服务或服务器信息，对应数组返回空 []
"""


class ImportConnectionsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        s = get_settings()
        self.client = AsyncOpenAI(api_key=s.dashscope_api_key, base_url=s.llm_base_url)
        self.model = s.mini_model

    async def extract(self, project_id: uuid.UUID) -> ExtractedConnections:
        # Fetch all documents
        result = await self.session.execute(
            select(ProjectDocument)
            .where(ProjectDocument.project_id == project_id)
            .order_by(ProjectDocument.created_at.asc())
        )
        documents = list(result.scalars().all())

        # Filter out agents_config and empty documents
        docs_with_content = [
            doc for doc in documents
            if doc.doc_type != "agents_config" and doc.content and doc.content.strip()
        ]

        if not docs_with_content:
            return ExtractedConnections(services=[], servers=[])

        # Build user prompt with all document content
        doc_sections = []
        for doc in docs_with_content:
            doc_sections.append(f"--- 文档: {doc.filename} ---\n{doc.content}")
        user_prompt = "请从以下项目文档中提取所有服务和服务器连接信息：\n\n" + "\n\n".join(doc_sections)

        # Call LLM
        log.info(
            "Extracting connections from documents",
            project_id=str(project_id),
            doc_count=len(docs_with_content),
        )
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        content = response.choices[0].message.content or "{}"
        log.info("LLM extraction completed", project_id=str(project_id))

        # Parse response
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            log.error("Failed to parse LLM response as JSON", content=content[:500])
            return ExtractedConnections(services=[], servers=[])

        services = [
            ExtractedService(**svc)
            for svc in data.get("services", [])
            if isinstance(svc, dict) and svc.get("name")
        ]
        servers = [
            ExtractedServer(**srv)
            for srv in data.get("servers", [])
            if isinstance(srv, dict) and srv.get("name")
        ]

        log.info(
            "Extraction results",
            project_id=str(project_id),
            services=len(services),
            servers=len(servers),
        )
        return ExtractedConnections(services=services, servers=servers)
