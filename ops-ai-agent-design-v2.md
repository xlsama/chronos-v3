# Ops AI Agent v2 — 完整系统设计文档

> 本文档用于指导实现一个面向运维场景的 AI Agent 系统（FastAPI + LangGraph + React）。请严格按照本文档的架构、数据模型、提示词和代码结构进行实现。

---

## 一、项目概述

### 产品定位

一个由事件驱动的运维 AI Agent 系统。事件（日志、报错、截图、描述文字）进入系统后，自动触发 Agent 流程：理解事件 → 定位服务/资源 → 执行排查命令 → 修复问题。全程通过 SSE 流式推送到前端，支持多用户同时观看，涉及危险操作时需要人工审批。

### 核心能力

- 手动触发 + Webhook 自动触发
- 多 Agent 编排（Supervisor + 3 个 Sub Agent）
- 通过 SSH / K8s Client / HTTP 连接远程基础设施
- 极简 8 Tool 设计：exec_read / exec_write + http_request + query_metrics / query_logs（可选） + 3 个知识检索 tool
- SSE 实时流式推送 Agent 思考过程和工具调用（支持多 Agent 阶段展示）
- Human-in-the-loop 权限审批机制（LangGraph interrupt/resume）
- 知识库 / Runbook / Incident History / Skills 四层记忆系统
- 学习闭环：Incident History → Runbook 定时聚合

---

## 二、技术栈

```
后端
├── Python 3.12
├── uv                              # 包管理
├── FastAPI                         # HTTP API + SSE
├── LangGraph                       # Agent 编排、Human-in-the-loop、流式输出
├── LangGraph Checkpoint (Postgres) # Agent 状态持久化，支持 interrupt/resume
├── PostgreSQL 17 + pgvector        # 业务数据 + 向量检索
├── Redis 7                         # Pub/Sub（SSE 多用户广播）
├── SQLAlchemy 2.x + asyncpg        # ORM + 异步数据库驱动
├── Alembic                         # 数据库迁移
├── paramiko                        # SSH 远程连接
├── kubernetes (官方 Python client) # K8s 操作
├── httpx                           # HTTP 探测 + 外部 API 调用 + Prometheus/Loki HTTP API（可选集成）
├── APScheduler                     # 定时任务
├── pydantic-settings               # 环境配置
├── loguru                          # 日志
├── orjson                          # JSON 序列化
├── pyjwt                           # 认证
├── poethepoet                      # Task runner
└── cryptography (Fernet)           # conn_config 字段加密

前端
├── React 19 + TanStack Router + Vite
├── TanStack Query + ofetch         # 数据请求
├── Tailwind CSS + shadcn/ui        # UI
├── Zustand                         # 状态管理
├── Streamdown                      # 流式 Markdown 渲染
├── EventSource API                 # SSE 接收
├── ahooks                          # React Hooks
├── Zod                             # 类型校验
├── Motion                          # 动画
└── pnpm                            # 包管理
```

---

## 三、数据库模型

### 3.1 projects（知识库项目）

```sql
CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(100) UNIQUE NOT NULL,    -- 用于 URL 和 _global 标识
    description TEXT,
    cloud_md    TEXT,                            -- 核心：描述资源与服务关系的 Markdown
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);

-- 项目文档（需求文档、架构文档等，分块后用于向量检索）
CREATE TABLE project_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID REFERENCES projects(id) ON DELETE CASCADE,
    filename    VARCHAR(255) NOT NULL,
    content     TEXT,
    doc_type    VARCHAR(50) DEFAULT 'general',  -- general / architecture / api / changelog
    status      VARCHAR(20) DEFAULT 'active',   -- active / archived
    created_at  TIMESTAMP DEFAULT now()
);

-- 文档分块 + 向量（与 project_documents 分开，支持重新分块）
CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES project_documents(id) ON DELETE CASCADE,
    project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(1536),
    created_at      TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_document_chunks_embedding ON document_chunks USING hnsw (embedding vector_cosine_ops);
```

### 3.2 infrastructures（基础设施）

```sql
CREATE TYPE infra_type AS ENUM ('ssh', 'kubernetes');
CREATE TYPE conn_status AS ENUM ('connected', 'disconnected', 'unknown');

CREATE TABLE infrastructures (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(id),
    name                VARCHAR(255) NOT NULL,          -- prod-server-01
    type                infra_type NOT NULL,            -- ssh / kubernetes
    display_type        VARCHAR(50) NOT NULL,           -- 服务器 / K8s Cluster
    conn_config         BYTEA NOT NULL,                 -- Fernet 加密的 JSONB
    -- ssh: {host, port, username, auth_type: password|key, ssh_key_ref?, password_ref?}
    -- kubernetes: {kubeconfig_ref, default_namespace, context}
    status              conn_status DEFAULT 'unknown',
    last_health_check   TIMESTAMP,
    tags                TEXT[] DEFAULT '{}',
    created_at          TIMESTAMP DEFAULT now(),
    updated_at          TIMESTAMP DEFAULT now()
);
```

### 3.3 services（服务）

```sql
CREATE TYPE service_type AS ENUM (
    'mysql', 'postgresql', 'redis', 'mongodb', 'elasticsearch',
    'nginx', 'apache', 'cron_job', 'systemd',
    'docker_container', 'k8s_deployment', 'k8s_statefulset',
    'java_app', 'node_app', 'python_app', 'custom'
);
CREATE TYPE discovery_method AS ENUM ('manual', 'auto_discovered');

CREATE TABLE services (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    infrastructure_id   UUID REFERENCES infrastructures(id) ON DELETE CASCADE,
    project_id          UUID REFERENCES projects(id),
    name                VARCHAR(255) NOT NULL,              -- mysql-orders
    service_type        service_type NOT NULL,
    discovery_method    discovery_method DEFAULT 'manual',
    business_context    TEXT,                                -- "承载活动报告数据的主数据库"
    health_cmd          VARCHAR(500),                       -- 健康检查命令
    log_path            VARCHAR(500),                       -- 日志路径
    config_path         VARCHAR(500),                       -- 配置文件路径
    metadata            JSONB DEFAULT '{}',                 -- 自动发现的额外信息
    status              conn_status DEFAULT 'unknown',
    created_at          TIMESTAMP DEFAULT now(),
    updated_at          TIMESTAMP DEFAULT now()
);
```

### 3.4 service_dependencies（服务依赖图）

```sql
CREATE TYPE dependency_type AS ENUM ('data_flow', 'api_call', 'config');

CREATE TABLE service_dependencies (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID REFERENCES projects(id) ON DELETE CASCADE,
    upstream_service_id     UUID REFERENCES services(id) ON DELETE CASCADE,
    downstream_service_id   UUID REFERENCES services(id) ON DELETE CASCADE,
    dependency_type         dependency_type NOT NULL,
    description             TEXT,
    created_at              TIMESTAMP DEFAULT now(),
    UNIQUE(upstream_service_id, downstream_service_id)
);
```

### 3.5 incidents（事件）

```sql
CREATE TYPE incident_status AS ENUM ('open', 'investigating', 'resolved', 'failed');
CREATE TYPE trigger_type AS ENUM ('manual', 'webhook');
CREATE TYPE input_type AS ENUM ('text', 'log', 'screenshot', 'webhook');

CREATE TABLE incidents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500),
    raw_input       TEXT NOT NULL,
    input_type      input_type DEFAULT 'text',
    attachments     JSONB DEFAULT '[]',             -- [{type: "image", url: "..."}, ...]
    status          incident_status DEFAULT 'open',
    trigger_type    trigger_type DEFAULT 'manual',
    project_id      UUID REFERENCES projects(id),
    thread_id       VARCHAR(255),                   -- LangGraph thread_id
    summary_md      TEXT,                           -- Summarize Agent 生成的报告
    saved_to_memory BOOLEAN DEFAULT false,
    created_at      TIMESTAMP DEFAULT now(),
    resolved_at     TIMESTAMP
);
```

### 3.6 incident_history（历史记忆）

```sql
CREATE TABLE incident_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID REFERENCES incidents(id),
    project_id      UUID REFERENCES projects(id),
    title           VARCHAR(500),
    summary_md      TEXT NOT NULL,
    tags            TEXT[] DEFAULT '{}',
    embedding       vector(1536),
    created_at      TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_incident_history_embedding ON incident_history USING hnsw (embedding vector_cosine_ops);
```

### 3.7 runbooks

```sql
CREATE TYPE publication_status AS ENUM ('draft', 'published');

CREATE TABLE runbooks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID REFERENCES projects(id),
    title       VARCHAR(255) NOT NULL,
    content     TEXT NOT NULL,
    tags        TEXT[] DEFAULT '{}',
    status      publication_status DEFAULT 'draft',
    embedding   vector(1536),
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_runbooks_embedding ON runbooks USING hnsw (embedding vector_cosine_ops);
```

### 3.8 skills

```sql
CREATE TABLE skills (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title                   VARCHAR(255) NOT NULL,
    content                 TEXT NOT NULL,               -- Markdown（带 frontmatter）
    tags                    TEXT[] DEFAULT '{}',
    applicable_service_types TEXT[] DEFAULT '{}',         -- 适用的服务类型
    is_preset               BOOLEAN DEFAULT false,
    created_at              TIMESTAMP DEFAULT now(),
    updated_at              TIMESTAMP DEFAULT now()
);
```

### 3.9 approval_requests（人工审批）

```sql
CREATE TYPE approval_status AS ENUM ('pending', 'approved', 'rejected', 'expired');
CREATE TYPE risk_level AS ENUM ('LOW', 'MEDIUM', 'HIGH');

CREATE TABLE approval_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID REFERENCES incidents(id),
    thread_id       VARCHAR(255) NOT NULL,
    infrastructure_id UUID REFERENCES infrastructures(id),
    service_id      UUID REFERENCES services(id),
    tool_name       VARCHAR(100) NOT NULL,
    command         TEXT NOT NULL,
    risk_level      risk_level NOT NULL,
    risk_detail     TEXT,
    rollback_plan   TEXT,
    explanation     TEXT,
    status          approval_status DEFAULT 'pending',
    requested_at    TIMESTAMP DEFAULT now(),
    decided_at      TIMESTAMP,
    decided_by      VARCHAR(255)
);
```

### 3.10 monitoring_sources（监控源配置）

```sql
CREATE TABLE monitoring_sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID REFERENCES projects(id) ON DELETE CASCADE,
    type        VARCHAR(50) NOT NULL,      -- prometheus | loki
    name        VARCHAR(255) NOT NULL,     -- "生产环境 Prometheus"
    endpoint    VARCHAR(500) NOT NULL,     -- http://prometheus:9090
    auth_config BYTEA,                     -- Fernet 加密（Bearer token / Basic auth）
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMP DEFAULT now(),
    updated_at  TIMESTAMP DEFAULT now()
);
```

> 监控源按项目配置，可选。Agent 在运行时检查项目是否配置了 Prometheus/Loki，有则启用 `query_metrics`/`query_logs` 工具。

### 3.11 messages（对话消息持久化）

```sql
CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool');

CREATE TABLE messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
    thread_id   VARCHAR(255) NOT NULL,
    role        message_role NOT NULL,
    content     TEXT,
    tool_calls  JSONB,                  -- LLM 返回的 tool_calls
    tool_name   VARCHAR(100),           -- tool message 的工具名
    metadata    JSONB DEFAULT '{}',     -- node name, token usage 等
    created_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_messages_thread ON messages(thread_id, created_at);
```

---

## 四、后端项目目录结构

```
backend/
├── pyproject.toml                      # uv 项目配置
├── alembic/                            # 数据库迁移
│   ├── alembic.ini
│   └── versions/
├── .env
│
├── src/
│   ├── main.py                         # FastAPI 入口
│   ├── config.py                       # pydantic-settings 环境配置
│   │
│   ├── api/
│   │   ├── __init__.py                 # Router 注册
│   │   ├── incidents.py                # 事件 CRUD + 触发
│   │   ├── approvals.py                # 审批接口
│   │   ├── stream.py                   # SSE 流式推送（Redis Pub/Sub）
│   │   ├── chat.py                     # 用户与 Agent 对话
│   │   ├── infrastructures.py          # Infrastructure CRUD + 连接测试
│   │   ├── services.py                 # Service CRUD + 自动发现
│   │   ├── projects.py                 # 项目 CRUD + cloud.md
│   │   ├── documents.py               # 项目文档上传 + 分块
│   │   ├── runbooks.py                # Runbook CRUD
│   │   ├── skills.py                   # Skills CRUD
│   │   ├── webhooks.py                 # Webhook 接收
│   │   └── upload.py                   # 文件上传（截图等）
│   │
│   ├── agent/
│   │   ├── graph.py                    # LangGraph 主 Graph 定义
│   │   ├── state.py                    # OpsState TypedDict
│   │   ├── nodes/
│   │   │   ├── gather_context.py       # 并行调用 3 个 Sub Agent
│   │   │   ├── main_agent.py           # 主 Agent（排查+修复）
│   │   │   ├── human_approval.py       # interrupt/resume 审批
│   │   │   └── summarize.py            # 总结 Agent
│   │   ├── sub_agents/
│   │   │   ├── kb_agent.py             # 知识库检索 Sub Agent
│   │   │   ├── history_agent.py        # 历史事件 Sub Agent
│   │   │   └── runbook_agent.py        # Runbook Sub Agent
│   │   └── prompts/
│   │       ├── main_agent.py
│   │       ├── kb_agent.py
│   │       ├── history_agent.py
│   │       ├── runbook_agent.py
│   │       └── summarize.py
│   │
│   ├── tools/
│   │   ├── __init__.py                 # READ_TOOLS / WRITE_TOOLS 导出
│   │   ├── exec_tools.py              # exec_read + exec_write（SSH/K8s 自动路由）
│   │   ├── http_tools.py              # http_request
│   │   ├── monitoring_tools.py        # query_metrics + query_logs（Prometheus/Loki）
│   │   ├── knowledge_tools.py         # search_knowledge_base + search_incident_history + search_runbook
│   │   └── safety.py                  # 命令白名单 + 输出压缩
│   │
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── ssh.py                      # paramiko SSH + SFTP
│   │   ├── k8s.py                      # kubernetes client
│   │   ├── http.py                     # httpx
│   │   ├── prometheus.py               # httpx — Prometheus HTTP API（PromQL 查询）
│   │   └── loki.py                     # httpx — Loki HTTP API（LogQL 查询）
│   │
│   ├── db/
│   │   ├── connection.py               # SQLAlchemy async engine + session
│   │   ├── models.py                   # SQLAlchemy ORM 模型
│   │   └── vector_store.py             # pgvector 检索封装
│   │
│   ├── services/                       # 业务逻辑层
│   │   ├── incident_service.py
│   │   ├── infrastructure_service.py
│   │   ├── service_catalog.py
│   │   ├── project_service.py
│   │   ├── document_service.py         # 分块 + embedding
│   │   ├── approval_service.py
│   │   ├── skill_service.py
│   │   └── crypto.py                   # Fernet 加密/解密 conn_config
│   │
│   ├── lib/
│   │   ├── logger.py                   # loguru 配置
│   │   ├── redis.py                    # redis.asyncio + Pub/Sub
│   │   ├── embedder.py                 # OpenAI / 本地 embedding
│   │   ├── reranker.py                 # 重排序
│   │   └── errors.py                   # 自定义异常
│   │
│   ├── scheduler/
│   │   └── runbook_updater.py          # 定时任务：Incident History → Runbook
│   │
│   └── skills/                         # 预设 Skills Markdown 文件
│       ├── mysql-troubleshooting.md
│       ├── redis-memory-analysis.md
│       ├── k8s-pod-crashloop.md
│       ├── linux-memory-oom.md
│       ├── network-connectivity.md
│       ├── cron-job-failure.md
│       └── nginx-troubleshooting.md
│
└── tests/
    ├── test_connectors/
    ├── test_tools/
    ├── test_agent/
    └── test_api/
```

---

## 五、Connector 层（连接器架构）

所有远程连接通过 Connector 层抽象，Tool 层不直接处理连接参数。

### 5.1 架构总览

```
Tool 层（agent 调用）
    ↓ 传入 infrastructure_id 或 service_id
Connector 层（连接管理）
    ↓ 从 DB 读取 conn_config → 解密 → 建立连接
远程基础设施
```

### 5.2 SSH Connector

```python
# connectors/ssh.py
import paramiko
from io import StringIO

class SSHConnector:
    """SSH 连接器，支持命令执行和 SFTP 文件传输"""

    async def exec_command(self, config: dict, command: str,
                           timeout: int = 30) -> tuple[str, str, int]:
        """
        执行远程命令，返回 (stdout, stderr, exit_code)
        config: {host, port, username, auth_type, ssh_key?, password?}
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs = {
                "hostname": config["host"],
                "port": config.get("port", 22),
                "username": config["username"],
                "timeout": 10,
            }
            if config["auth_type"] == "key":
                key = paramiko.RSAKey.from_private_key(StringIO(config["ssh_key"]))
                connect_kwargs["pkey"] = key
            else:
                connect_kwargs["password"] = config["password"]

            client.connect(**connect_kwargs)
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return stdout.read().decode(), stderr.read().decode(), exit_code
        finally:
            client.close()

    async def sftp_download(self, config: dict, remote_path: str) -> bytes:
        """下载远程文件"""
        # ... paramiko SFTP 实现

    async def sftp_upload(self, config: dict, local_content: bytes, remote_path: str):
        """上传文件到远程"""
        # ... paramiko SFTP 实现

    async def test_connection(self, config: dict) -> bool:
        """测试 SSH 连接是否可用"""
        try:
            stdout, _, code = await self.exec_command(config, "echo ok", timeout=5)
            return code == 0 and "ok" in stdout
        except Exception:
            return False
```

### 5.3 K8s Connector

```python
# connectors/k8s.py
from kubernetes import client, config as k8s_config
from kubernetes.stream import stream
import tempfile, yaml

class K8sConnector:
    """Kubernetes 连接器"""

    def _load_config(self, conn_config: dict) -> client.ApiClient:
        """从 kubeconfig 内容加载配置"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(conn_config["kubeconfig"])
            f.flush()
            k8s_config.load_kube_config(config_file=f.name, context=conn_config.get("context"))
        return client.ApiClient()

    async def get_resources(self, config: dict, resource_type: str,
                            namespace: str = None, name: str = None) -> str:
        """kubectl get <resource_type> [-n namespace] [name]"""
        api_client = self._load_config(config)
        # 根据 resource_type 路由到对应的 API
        # pods → CoreV1Api.list_namespaced_pod
        # deployments → AppsV1Api.list_namespaced_deployment
        # services → CoreV1Api.list_namespaced_service
        # ...

    async def describe_resource(self, config: dict, resource_type: str,
                                 name: str, namespace: str) -> str:
        """kubectl describe"""

    async def get_logs(self, config: dict, pod: str, namespace: str,
                       container: str = None, lines: int = 200) -> str:
        """kubectl logs"""

    async def exec_in_pod(self, config: dict, pod: str, namespace: str,
                          command: str, container: str = None) -> str:
        """kubectl exec — 带 distroless 降级处理"""
        try:
            return await self._exec_raw(config, pod, namespace, command, container)
        except Exception as e:
            if "executable file not found" in str(e):
                return await self._fallback_without_shell(config, pod, namespace)
            raise

    async def apply_manifest(self, config: dict, manifest_yaml: str) -> str:
        """kubectl apply -f"""

    async def _fallback_without_shell(self, config, pod, namespace) -> str:
        """distroless 镜像降级：logs + describe + top"""
        logs = await self.get_logs(config, pod, namespace, lines=200)
        desc = await self.describe_resource(config, "pod", pod, namespace)
        return f"[容器无 Shell，自动降级]\n\n## Logs\n{logs}\n\n## Describe\n{desc}"

    async def test_connection(self, config: dict) -> bool:
        try:
            api_client = self._load_config(config)
            v1 = client.CoreV1Api(api_client)
            v1.list_namespace(limit=1)
            return True
        except Exception:
            return False
```

### 5.4 HTTP Connector

```python
# connectors/http.py
import httpx

class HTTPConnector:
    """HTTP 连接器 — 用于健康检查和 API 探测"""

    async def request(self, url: str, method: str = "GET",
                      headers: dict = None, body: str = None,
                      timeout: int = 10) -> str:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            response = await client.request(
                method=method, url=url, headers=headers, content=body,
            )
            return (
                f"Status: {response.status_code}\n"
                f"Headers: {dict(response.headers)}\n"
                f"Body:\n{response.text[:4000]}"
            )
```

### 5.5 Prometheus Connector

```python
# connectors/prometheus.py
import httpx

class PrometheusConnector:
    """Prometheus HTTP API 连接器 — 用于 PromQL 指标查询"""

    async def query_range(self, endpoint: str, promql: str,
                          start: str, end: str, step: str = "60s",
                          auth_config: dict = None,
                          timeout: int = 15) -> str:
        """
        Prometheus range query API
        endpoint: http://prometheus:9090
        promql: rate(node_cpu_seconds_total{mode!="idle"}[5m])
        """
        headers = self._build_auth_headers(auth_config)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{endpoint}/api/v1/query_range",
                params={"query": promql, "start": start, "end": end, "step": step},
                headers=headers,
            )
            data = response.json()
            if data.get("status") != "success":
                return f"Prometheus 查询失败: {data.get('error', 'unknown error')}"
            return self._format_result(data["data"])

    async def query_instant(self, endpoint: str, promql: str,
                            auth_config: dict = None,
                            timeout: int = 15) -> str:
        """Prometheus instant query API"""
        headers = self._build_auth_headers(auth_config)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{endpoint}/api/v1/query",
                params={"query": promql},
                headers=headers,
            )
            data = response.json()
            if data.get("status") != "success":
                return f"Prometheus 查询失败: {data.get('error', 'unknown error')}"
            return self._format_result(data["data"])

    def _build_auth_headers(self, auth_config: dict = None) -> dict:
        if not auth_config:
            return {}
        if auth_config.get("type") == "bearer":
            return {"Authorization": f"Bearer {auth_config['token']}"}
        if auth_config.get("type") == "basic":
            import base64
            cred = base64.b64encode(
                f"{auth_config['username']}:{auth_config['password']}".encode()
            ).decode()
            return {"Authorization": f"Basic {cred}"}
        return {}

    def _format_result(self, data: dict) -> str:
        """将 Prometheus 响应格式化为 Agent 可读文本"""
        result_type = data.get("resultType", "")
        results = data.get("result", [])
        if not results:
            return "查询无结果"

        lines = [f"类型: {result_type}, 共 {len(results)} 条时间序列\n"]
        for series in results[:20]:  # 限制返回条数
            metric = series.get("metric", {})
            label_str = ", ".join(f'{k}="{v}"' for k, v in metric.items())
            if result_type == "matrix":
                values = series.get("values", [])
                lines.append(f"  {{{label_str}}} ({len(values)} 个数据点)")
                for ts, val in values[-5:]:  # 只展示最近 5 个点
                    lines.append(f"    {ts}: {val}")
            else:
                value = series.get("value", [None, "N/A"])
                lines.append(f"  {{{label_str}}} = {value[1]}")
        return "\n".join(lines)

    async def test_connection(self, endpoint: str, auth_config: dict = None) -> bool:
        try:
            headers = self._build_auth_headers(auth_config)
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{endpoint}/api/v1/status/buildinfo", headers=headers)
                return response.status_code == 200
        except Exception:
            return False
```

### 5.6 Loki Connector

```python
# connectors/loki.py
import httpx

class LokiConnector:
    """Loki HTTP API 连接器 — 用于 LogQL 日志查询"""

    async def query_range(self, endpoint: str, logql: str,
                          start: str = None, end: str = None,
                          limit: int = 100,
                          auth_config: dict = None,
                          timeout: int = 15) -> str:
        """
        Loki query_range API
        endpoint: http://loki:3100
        logql: {job="nginx"} |= "error" | logfmt | status >= 500
        """
        headers = self._build_auth_headers(auth_config)
        params = {"query": logql, "limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{endpoint}/loki/api/v1/query_range",
                params=params,
                headers=headers,
            )
            data = response.json()
            if data.get("status") != "success":
                return f"Loki 查询失败: {data.get('error', 'unknown error')}"
            return self._format_result(data["data"])

    def _build_auth_headers(self, auth_config: dict = None) -> dict:
        if not auth_config:
            return {}
        if auth_config.get("type") == "bearer":
            return {"Authorization": f"Bearer {auth_config['token']}"}
        if auth_config.get("type") == "basic":
            import base64
            cred = base64.b64encode(
                f"{auth_config['username']}:{auth_config['password']}".encode()
            ).decode()
            return {"Authorization": f"Basic {cred}"}
        return {}

    def _format_result(self, data: dict) -> str:
        """将 Loki 响应格式化为 Agent 可读文本"""
        results = data.get("result", [])
        if not results:
            return "查询无日志结果"

        lines = [f"共 {len(results)} 个日志流\n"]
        for stream in results[:10]:
            labels = stream.get("stream", {})
            label_str = ", ".join(f'{k}="{v}"' for k, v in labels.items())
            entries = stream.get("values", [])
            lines.append(f"--- {{{label_str}}} ({len(entries)} 条日志) ---")
            for ts, log_line in entries[-50:]:  # 最多展示 50 条
                lines.append(log_line)
        return "\n".join(lines)

    async def test_connection(self, endpoint: str, auth_config: dict = None) -> bool:
        try:
            headers = self._build_auth_headers(auth_config)
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{endpoint}/ready", headers=headers)
                return response.status_code == 200
        except Exception:
            return False
```

---

## 六、Agent 架构设计

### 6.1 LangGraph State 定义

```python
# agent/state.py
class OpsState(TypedDict):
    # 事件信息
    incident_id: str
    raw_input: str                      # 原始事件内容
    input_type: str                     # text / log / screenshot
    attachments: list[dict]             # [{type: "image", url: "..."}]

    # 主 Agent 消息（滚动窗口）
    messages: Annotated[list, add_messages]

    # Sub Agent 返回的摘要（只存摘要，防 context 爆炸）
    kb_summary: Optional[str]           # 知识库背景
    incident_history_summary: Optional[str]  # 历史相似事件
    runbook_summary: Optional[str]      # 相关 Runbook
    matched_skills: Optional[str]       # 匹配到的 Skills 内容

    # 执行上下文
    identified_project: Optional[str]   # 定位到的项目 ID
    identified_services: list[dict]     # Agent 定位到的服务列表
    investigation_log: list[dict]       # 排查过程记录 [{step, hypothesis, command, finding}]

    # 审批相关
    pending_approval: Optional[dict]
    approval_result: Optional[str]      # approved / rejected

    # 最终输出
    summary_md: Optional[str]
    is_complete: bool
```

### 6.2 主 Graph 结构

```
                    ┌─────────────────┐
                    │  gather_context  │  并行调用 3 个 Sub Agent
                    │  (KB + History   │  + 匹配 Skills
                    │   + Runbook)     │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
               ┌───►│   main_agent    │◄──────────────┐
               │    │  (排查 + 修复)   │               │
               │    └────────┬────────┘               │
               │             │                        │
               │    ┌────────▼────────┐               │
               │    │  route_decision │               │
               │    └──┬──────┬──────┬┘               │
               │       │      │      │                │
               │  continue  need   complete           │
               │       │   approval    │              │
               │       │      │        │              │
               └───────┘ ┌────▼─────┐  │              │
                         │  human   │  │              │
                         │ approval │──┘──────────────┘
                         │(interrupt│  (approved → main_agent)
                         │ /resume) │
                         └──────────┘
                                       │
                              ┌────────▼────────┐
                              │   summarize     │
                              │  (生成报告)      │
                              └────────┬────────┘
                                       │
                                      END
```

```python
# agent/graph.py
def build_graph(checkpointer):
    graph = StateGraph(OpsState)

    graph.add_node("gather_context", gather_context_node)
    graph.add_node("main_agent", main_agent_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("summarize", summarize_node)

    graph.set_entry_point("gather_context")
    graph.add_edge("gather_context", "main_agent")
    graph.add_conditional_edges("main_agent", route_after_main_agent, {
        "need_approval": "human_approval",
        "complete": "summarize",
        "continue": "main_agent",
    })
    graph.add_edge("human_approval", "main_agent")
    graph.add_edge("summarize", END)

    return graph.compile(checkpointer=checkpointer)
```

### 6.3 gather_context 节点

并行调用 3 个 Sub Agent + 匹配 Skills，各自独立运行，只返回摘要给主 State：

```python
async def gather_context_node(state: OpsState) -> dict:
    kb_result, history_result, runbook_result, skills_result = await asyncio.gather(
        run_kb_agent(state["raw_input"]),
        run_incident_history_agent(state["raw_input"]),
        run_runbook_agent(state["raw_input"]),
        match_skills(state["raw_input"]),  # 基于标签 + 语义匹配
    )
    return {
        "kb_summary": kb_result,                    # ≤500 token
        "incident_history_summary": history_result,  # ≤300 token
        "runbook_summary": runbook_result,           # ≤300 token
        "matched_skills": skills_result,             # ≤500 token
    }
```

每个 Sub Agent 内部维护独立的 messages，可以多轮调用工具，但最终只返回一段精简摘要。

### 6.4 main_agent 节点

```python
async def main_agent_node(state: OpsState) -> dict:
    # 构建动态 context 注入
    context = build_context(state)  # 包含 Sub Agent 摘要 + Skills + 当前事件
    system_msg = SystemMessage(content=MAIN_AGENT_PROMPT + "\n\n" + context)

    # 滚动截断历史消息，保留最近 8000 token
    trimmed = trim_messages(state["messages"], max_tokens=8000, strategy="last",
                            token_counter=llm, include_system=True)

    response = await llm_with_tools.ainvoke([system_msg] + trimmed)

    new_state = {"messages": [response]}
    # 检查是否调用了 WRITE 工具 → 触发审批
    for tool_call in response.tool_calls:
        if tool_call["name"] in WRITE_TOOL_NAMES:
            approval = await create_approval_request(tool_call, state["incident_id"])
            new_state["pending_approval"] = approval
            break
    return new_state
```

### 6.5 Human-in-the-loop 审批节点

```python
async def human_approval_node(state: OpsState) -> dict:
    pending = state["pending_approval"]

    # LangGraph interrupt：自动暂停，状态持久化到 PostgreSQL
    # 前端点击批准/拒绝后，通过 /approvals/{id}/decide 接口调用 Command(resume=...)
    decision = interrupt({
        "approval_id": pending["approval_id"],
        "command": pending["command"],
        "tool_name": pending["tool_name"],
        "infrastructure_id": pending.get("infrastructure_id"),
        "service_id": pending.get("service_id"),
        "risk_level": pending["risk_level"],
        "risk_detail": pending["risk_detail"],
        "rollback_plan": pending["rollback_plan"],
        "explanation": pending["explanation"],
    })

    return {
        "approval_result": decision,   # "approved" 或 "rejected"
        "pending_approval": None,
    }
```

### 6.6 Context 窗口管理策略

| 来源 | Token 预算 | 管理方式 |
|------|-----------|---------|
| Sub Agent 摘要（KB + History + Runbook） | 各 300-500 | Sub Agent 内部控制输出长度 |
| 匹配 Skills 内容 | ≤500 | 只注入最相关的 1-2 个 Skill 的精简版 |
| 工具输出 | 单次 ≤4000 字符 | 超过阈值自动压缩（头+尾+LLM摘要） |
| 历史 messages | 滚动窗口 8000 token | `trim_messages(strategy="last")` |
| System Prompt | ~2000 | 固定 |

**总 context 上限目标：~15000 token / 轮**

---

## 七、Tool 设计（极简 8 Tool）

### 设计原则

像 Claude Code 一样，只保留最简单的几个原语。LLM 足够聪明，自己能拼命令。

- `exec_read` + `exec_write` — 万能命令执行，LLM 自己拼所有命令（含 docker CLI）
- `http_request` — 独立的 HTTP 连接方式，用于健康检查和 API 探测
- `query_metrics` + `query_logs` — 可选的监控集成，项目配置了 Prometheus/Loki 后自动启用
- 3 个知识检索 tool — 语义清晰，Sub Agent 各用各的

**无数据库直连** — 数据库查询统一走 SSH 执行 CLI（`mysql -e` / `psql -c` / `redis-cli`），不搞 Python driver 直连。简单直接。

### 7.1 完整 Tool 列表

| Tool | 分类 | 参数 | 说明 | 可用条件 |
|------|------|------|------|---------|
| `exec_read` | READ | infrastructure_id, command | 在远程执行只读命令（SSH/K8s 自动路由）。白名单校验。 | 始终可用 |
| `exec_write` | WRITE | infrastructure_id, command, explanation, risk_level, risk_detail, rollback_plan | 在远程执行写命令，需审批 | 始终可用 |
| `http_request` | READ | url, method, headers, body, timeout | HTTP 探测 / API 健康检查 | 始终可用 |
| `query_metrics` | READ | project_id, promql, time_range | 查询 Prometheus/VictoriaMetrics（PromQL），返回指标趋势 | 项目已配置 Prometheus 监控源 |
| `query_logs` | READ | project_id, logql, limit | 查询 Loki（LogQL），返回日志检索结果 | 项目已配置 Loki 日志源 |
| `search_knowledge_base` | READ | query, project_id | 知识库检索（cloud.md + 项目文档） | 始终可用 |
| `search_incident_history` | READ | query, project_id | 历史事件检索 | 始终可用 |
| `search_runbook` | READ | query, project_id | Runbook 检索 | 始终可用 |

> **工具可用条件说明**：`query_metrics` 和 `query_logs` 是可选工具。Agent 启动时检查项目的 `monitoring_sources` 表，如果配置了对应类型的监控源则注入该工具，否则不注入。无监控源时 Agent 退回使用 `exec_read` 执行命令行日志/指标查看。

### 7.2 exec_read / exec_write 命令路由

根据 `infrastructure_id` 对应的 `infra_type` 自动选择 Connector：

| infra_type | 路由方式 | 命令示例 |
|------------|---------|---------|
| `ssh` | SSH Connector → paramiko exec_command | `free -m`, `crontab -l`, `mysql -e "SELECT ..."`, `docker ps` |
| `kubernetes` | K8s Connector → kubectl exec / API | `kubectl get pods -n default`, `kubectl logs xxx` |

### 7.3 LLM 自己拼命令的示例

Agent 只需要 `exec_read` 就能覆盖所有排查场景：

```
# 查数据库
exec_read(infra_id, 'mysql -u root -p"$MYSQL_PWD" -e "SELECT MAX(activity_date) FROM activity_reports"')
exec_read(infra_id, 'psql -U postgres -c "SELECT * FROM pg_stat_activity"')
exec_read(infra_id, 'redis-cli INFO memory')

# 查服务状态
exec_read(infra_id, 'systemctl status nginx')
exec_read(infra_id, 'kubectl get pods -n production')
exec_read(infra_id, 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"')

# 查日志
exec_read(infra_id, 'journalctl -u sync-job --since "2026-01-18" --no-pager | tail -100')
exec_read(infra_id, 'tail -500 /var/log/nginx/error.log | grep -i "error\|upstream"')
exec_read(infra_id, 'kubectl logs deployment/order-service -n default --tail=200')

# 查资源
exec_read(infra_id, 'free -m')
exec_read(infra_id, 'df -h')
exec_read(infra_id, 'top -bn1 | head -20')

# 查定时任务
exec_read(infra_id, 'crontab -l')
exec_read(infra_id, 'systemctl list-timers --all')
```

### 7.4 Sub Agent 工具分配

| Agent | 工具 |
|-------|------|
| Supervisor（主 Agent） | `exec_read`, `exec_write`, `http_request`, `query_metrics`*, `query_logs`*, `search_knowledge_base`, `search_incident_history`, `search_runbook` |
| KB Agent | `search_knowledge_base` |
| History Agent | `search_incident_history` |
| Runbook Agent | `search_runbook` |

> *标注 `*` 的工具仅在项目配置了对应监控源时注入。

### 7.5 输出压缩策略

工具输出超过 4000 字符时自动压缩：

```python
async def compress_output(result: str, max_chars: int = 4000) -> str:
    if len(result) <= max_chars:
        return result

    head = result[:1000]       # 保留头部（状态/标题）
    tail = result[-2000:]      # 保留尾部（最新数据）

    middle_summary = await llm.ainvoke(
        f"简洁总结以下命令输出的关键信息：\n{result}"
    )

    return (
        f"{head}\n\n"
        f"[... 已压缩，原始 {len(result)} 字符 ...]\n\n"
        f"{middle_summary}\n\n"
        f"[最后部分]\n{tail}"
    )
```

---

## 八、SSE 流式推送

### 8.1 架构

```
Agent (LangGraph astream_events)
    ↓ 发布事件
Redis Pub/Sub (channel: incident:{id})
    ↓ 订阅
FastAPI SSE endpoint (/incidents/{id}/stream)
    ↓ 推送
多个前端用户 (EventSource)
```

使用 Redis Pub/Sub 实现多用户订阅同一事件流。Agent 执行时将事件发布到 Redis channel，SSE endpoint 订阅该 channel 并推送给所有连接的客户端。

### 8.2 SSE 事件结构

每个 SSE 事件携带 `phase` 和 `agent` 字段，标识事件来源，支持前端多 Agent 阶段展示：

```typescript
interface SSEEvent {
  type: "thinking" | "tool_start" | "tool_end" | "approval_required" | "approval_decided" | "phase_change" | "summary" | "error"

  // 标识事件来源
  phase: "gather_context" | "main_agent" | "summarize"
  agent: "supervisor" | "kb" | "history" | "runbook" | "summarize"

  // 原有字段
  content?: string       // thinking
  tool?: string          // tool_start/end
  input?: any            // tool_start
  output?: string        // tool_end
  approval?: object      // approval_required
}
```

### 8.3 SSE 事件类型

| type | 含义 | payload |
|------|------|---------|
| `thinking` | LLM 正在生成 token | `{content, phase, agent}` |
| `tool_start` | 工具开始调用 | `{tool, input, phase, agent}` |
| `tool_end` | 工具调用完成 | `{tool, output, phase, agent}` |
| `phase_change` | 阶段切换通知 | `{phase}` |
| `approval_required` | 需要人工审批 | `{approval_id, command, risk_level, ...}` |
| `approval_decided` | 审批结果 | `{approval_id, decision}` |
| `summary` | 最终报告 | `{summary_md}` |
| `error` | 错误 | `{message}` |

### 8.4 FastAPI SSE 接口

```python
@router.get("/incidents/{incident_id}/stream")
async def stream_incident(incident_id: str):
    async def event_generator():
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"incident:{incident_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data'].decode()}\n\n"
        finally:
            await pubsub.unsubscribe(f"incident:{incident_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

### 8.5 Agent 事件发布（带 phase/agent 标识）

Agent 执行过程中，通过 `astream_events` 捕获事件并注入 `phase`/`agent` 字段后发布到 Redis：

```python
# gather_context 阶段 — 各 Sub Agent 独立发布
async def run_kb_agent(incident_id: str, raw_input: str):
    async for event in kb_llm.astream_events(...):
        sse_payload = transform_event(event)
        if sse_payload:
            await redis.publish(f"incident:{incident_id}", orjson.dumps({
                **sse_payload,
                "phase": "gather_context",
                "agent": "kb",
            }))

async def run_history_agent(incident_id: str, raw_input: str):
    async for event in history_llm.astream_events(...):
        sse_payload = transform_event(event)
        if sse_payload:
            await redis.publish(f"incident:{incident_id}", orjson.dumps({
                **sse_payload,
                "phase": "gather_context",
                "agent": "history",
            }))

# main_agent 阶段
async def run_main_agent(incident_id: str, state: OpsState):
    # 发布阶段切换事件
    await redis.publish(f"incident:{incident_id}", orjson.dumps({
        "type": "phase_change",
        "phase": "main_agent",
    }))
    async for event in main_llm.astream_events(...):
        sse_payload = transform_event(event)
        if sse_payload:
            await redis.publish(f"incident:{incident_id}", orjson.dumps({
                **sse_payload,
                "phase": "main_agent",
                "agent": "supervisor",
            }))
```

---

## 九、审批机制

### 9.1 完整流程

```
1. main_agent 调用 WRITE 工具
2. → 创建 approval_request 记录（status=pending）
3. → 设置 state.pending_approval
4. → route_decision → "need_approval"
5. → human_approval_node → interrupt()
6. → LangGraph 暂停，状态持久化到 PostgreSQL
7. → SSE 推送 approval_required 给前端
8. → 前端渲染审批卡片（命令 + 风险 + 回滚方案 + 批准/拒绝按钮）
9. → 用户点击批准/拒绝
10. → POST /approvals/{id}/decide
11. → 更新 approval_request 记录
12. → Command(resume="approved") 恢复 LangGraph
13. → human_approval_node 返回 approval_result
14. → 回到 main_agent 继续执行
```

### 9.2 审批请求数据

每个 WRITE 工具调用必须携带以下信息（由 Agent 在 tool_call 参数中提供）：

| 字段 | 说明 | 示例 |
|------|------|------|
| `explanation` | 操作说明 | "重启 sync-job 定时任务以恢复数据同步" |
| `risk_level` | LOW / MEDIUM / HIGH | "MEDIUM" |
| `risk_detail` | 风险说明 | "重启期间约 30 秒无法同步数据" |
| `rollback_plan` | 回滚方案 | "systemctl stop sync-job && 恢复旧配置" |

### 9.3 风险等级定义

| 级别 | 定义 | 示例操作 |
|------|------|---------|
| LOW | 影响单个非关键服务，可秒级回滚 | 重启非核心 cron job |
| MEDIUM | 影响单个关键服务，有明确回滚方案 | 重启数据库、修改配置、扩缩容 |
| HIGH | 影响多个服务、数据变更、不可逆操作 | DELETE/DROP SQL、rm 文件、K8s 大规模变更 |

---

## 十、Agent 提示词

### 10.1 主 Agent System Prompt

```
你是一名专业的 SRE（站点可靠性工程师）AI Agent。
你的任务是调查运维事件，诊断根因，并在远程基础设施上修复问题。

## 你的工具

你有 8 个工具，它们足以覆盖所有运维场景。你足够聪明，可以自己拼命令。

### 只读工具
- exec_read(infrastructure_id, command) — 在远程执行只读命令（SSH/K8s 自动路由），白名单校验
- http_request(url, method, headers, body, timeout) — HTTP 探测 / API 健康检查
- query_metrics(project_id, promql, time_range) — 查询 Prometheus 指标（仅在项目配置了 Prometheus 时可用）
- query_logs(project_id, logql, limit) — 查询 Loki 日志（仅在项目配置了 Loki 时可用）
- search_knowledge_base(query, project_id) — 知识库检索（cloud.md + 项目文档）
- search_incident_history(query, project_id) — 历史事件检索
- search_runbook(query, project_id) — Runbook 检索

### 写工具（需审批）
- exec_write(infrastructure_id, command, explanation, risk_level, risk_detail, rollback_plan) — 在远程执行写命令

## 工具选择优先级

1. 查看指标趋势 → query_metrics（PromQL），如果项目配置了 Prometheus
   例: rate(node_cpu_seconds_total{mode!="idle"}[5m])
   例: node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes

2. 查看日志 → query_logs（LogQL），如果项目配置了 Loki
   例: {job="nginx"} |= "error" | logfmt | status >= 500

3. 实时状态/深入排查 → exec_read + Shell 命令
   当 1-2 不可用或不够用时使用

4. HTTP 健康检查 → http_request

5. 修复 → exec_write（自动触发审批）

## 命令拼写示例

exec_read 是万能命令执行，你自己拼所有命令（包括 docker CLI）：

```
# 查数据库
exec_read(infra_id, 'mysql -u root -p"$MYSQL_PWD" -e "SELECT MAX(activity_date) FROM activity_reports"')
exec_read(infra_id, 'psql -U postgres -c "SELECT * FROM pg_stat_activity"')
exec_read(infra_id, 'redis-cli INFO memory')

# 查服务状态
exec_read(infra_id, 'systemctl status nginx')
exec_read(infra_id, 'kubectl get pods -n production')
exec_read(infra_id, 'docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"')

# 查日志
exec_read(infra_id, 'journalctl -u sync-job --since "2026-01-18" --no-pager | tail -100')
exec_read(infra_id, 'tail -500 /var/log/nginx/error.log | grep -i "error\|upstream"')
exec_read(infra_id, 'kubectl logs deployment/order-service -n default --tail=200')

# 查资源
exec_read(infra_id, 'free -m')
exec_read(infra_id, 'df -h')
exec_read(infra_id, 'top -bn1 | head -20')

# 查定时任务
exec_read(infra_id, 'crontab -l')
exec_read(infra_id, 'systemctl list-timers --all')

# Docker 容器（通过 SSH exec_read）
exec_read(infra_id, 'docker logs --tail=200 nginx-proxy')
exec_read(infra_id, 'docker exec mysql-db mysql -e "SHOW PROCESSLIST"')
exec_read(infra_id, 'docker stats --no-stream')
```

## 排查思维框架（每次严格按此顺序）
1. **理解**：仔细阅读事件内容。什么服务？什么症状？什么时间？
2. **定位**：用 search_knowledge_base 找到涉及的项目和服务
3. **建立假设**：在执行任何命令前，提出 2~3 个可能的根因假设
4. **排查**：用 exec_read 逐一验证或排除假设
5. **确认根因**：明确陈述确认的根因和证据
6. **制定修复计划**：描述要执行的操作、风险和回滚方案
7. **修复**：用 exec_write 执行写操作（自动触发审批）
8. **验证**：修复后用 exec_read 确认问题已解决

## 命令编写规范
- 每次只执行一个聚焦的命令
- 优先用机器可读格式：free -m, df -h, ps aux --sort=-%mem | head -20
- 日志用 grep 加上下文：grep -i "error\|exception\|fatal" /var/log/app.log | tail -100
- 数据库查询统一走 CLI：mysql -e / psql -c / redis-cli，不直连
- 避免宽泛命令：不要 find / -name "*.log"

## K8s distroless 降级
kubectl exec 失败时按此顺序降级：
1. kubectl logs --tail=500 --timestamps
2. kubectl describe pod
3. kubectl top pod
4. 找到 Node → SSH 到宿主机排查
永远不说"无法排查因为容器没有 shell"。

## 请求写操作格式
调用 exec_write 前，必须在消息中输出：

---
## ⚠️ 申请执行写操作
**目标：** {infrastructure 名称}
**命令：**
```
{command}
```
**操作说明：** {explanation}
**必要性：** {关联诊断结论}
**风险等级：** LOW / MEDIUM / HIGH
**风险说明：** {risk_detail}
**回滚方案：** {rollback_plan}
---

## 思考过程格式
🔍 **假设：** {当前验证的假设}
🛠️ **下一步：** {要用什么工具，为什么}
📊 **发现：** {工具输出告诉我什么}
✅ / ❌ **假设状态：** {已确认 / 已排除 / 需要更多数据}
```

### 10.2 KB Agent Prompt

```
你是知识库检索 Agent。
根据事件内容，从知识库中检索相关的项目背景和服务架构信息。

执行步骤：
1. 从事件中提取关键词（服务名、错误类型、资源名等）
2. 用 search_knowledge_base 检索相关内容（自动包含 cloud.md + 项目文档）
3. 整理成简洁的摘要返回

返回格式（严格控制在 500 token 以内）：

## 相关项目
[项目名称和简介]

## 涉及的服务
[服务名 + service_type + infrastructure + business_context]

## 服务依赖
[数据流向图]

## 业务背景
[这些服务承担什么业务功能]

如果没有找到，返回"知识库中暂无相关项目信息"。
```

### 10.3 Incident History Agent Prompt

```
你是历史事件检索 Agent。
查找与当前事件相似的历史事件，帮助主 Agent 借鉴过去的解决经验。

执行步骤：
1. 从事件中提取关键词
2. 用 search_incident_history 检索
3. 整理成摘要

返回格式（严格 300 token 以内）：

## 相似历史事件
[事件标题] - [发生时间]
- 根因：[简短描述]
- 解决方案：[具体操作]
- 关键命令：[可参考的命令]

没有找到则返回"暂无相似历史事件"。
```

### 10.4 Runbook Agent Prompt

```
你是 Runbook 检索 Agent。
找到与当前事件相关的标准操作流程（SOP）。

执行步骤：
1. 提取服务类型和问题类型
2. 用 search_runbook 检索（自动包含 _global 项目的 Runbook）
3. 整理成摘要

返回格式（严格 300 token 以内）：

## 相关 Runbook
[Runbook 标题]
- 关键排查步骤：[提炼核心步骤]
- 推荐工具：[应该用什么工具]
- 注意事项：[重要提示]

没有找到则返回"暂无相关 Runbook"。
```

### 10.5 Summarize Agent Prompt

```
你是事件报告生成 Agent。
根据主 Agent 完整的排查过程，生成结构化的事件报告。

输出格式（Markdown）：

# 事件报告：{一行标题}

## 摘要
[2~3 句话：发生了什么、影响、如何解决]

## 时间线
| 时间 | 事件 |
|------|------|
| T+0  | 事件触发 |
| T+Xm | [关键排查步骤] |
| T+Xm | [修复操作] |
| T+Xm | [确认解决] |

## 根因分析
[技术性根因描述，解释为什么会发生]

## 影响范围
- 受影响服务：
- 受影响基础设施：
- 持续时长：

## 排查过程
[关键命令和发现]

## 修复操作
[实际执行的修复命令]

## 验证结果
[如何确认问题已解决]

## 预防建议
[1~3 条可操作的预防措施]

---
*由 Ops AI Agent 自动生成*
```

---

## 十一、Skills 系统

### 11.1 设计理念

Skills 是 Agent 的"方法论手册"，不绑定具体的工具实现，而是指导 Agent 用什么工具、什么命令、按什么顺序排查。Skills 在 gather_context 阶段基于事件内容匹配，动态注入到主 Agent 的 system prompt 中。

### 11.2 Skill 格式（Markdown + frontmatter）

```markdown
---
title: MySQL 故障排查
tags: [mysql, database, slow_query, connection, replication]
applicable_service_types: [mysql]
---

## 排查步骤

### 1. 检查连接状态
- 命令: `exec_read(infra_id, 'mysql -u root -e "SHOW STATUS LIKE \'Threads_%\'"')`
- 关注: Threads_connected > max_connections 的 80% 说明连接即将耗尽

### 2. 检查慢查询
- 命令: `exec_read(infra_id, 'mysql -u root -e "SELECT * FROM information_schema.processlist WHERE Time > 10"')`
- 命令: `exec_read(infra_id, 'mysql -u root -e "SHOW STATUS LIKE \'Slow_queries\'"')`

### 3. 检查复制状态（如果是主从架构）
- 命令: `exec_read(infra_id, 'mysql -u root -e "SHOW SLAVE STATUS\\G"')`
- 关注: Seconds_Behind_Master, Slave_IO_Running, Slave_SQL_Running

### 4. 检查磁盘空间
- 命令: `exec_read(infra_id, 'df -h')`
- MySQL binlog 和 data 目录可能占满磁盘

### 5. 检查错误日志
- 命令: `exec_read(infra_id, 'tail -200 /var/log/mysql/error.log')`
```

### 11.3 匹配策略

```
1. 从事件内容中提取关键词和 service_type
2. 基于 tags + applicable_service_types 匹配候选 Skills
3. 如果候选 > 2 个，用 embedding 相似度排序
4. 取 Top 1-2 个 Skill，精简后注入 system prompt
```

### 11.4 主 Agent System Prompt 完整注入结构

```
系统角色定义
+ 排查思维框架
+ 工具列表和使用规则
+ 命令编写规范
+ 约束规则
───── 动态注入部分 ─────
+ ## 当前事件
  {raw_input + attachments}
+ ## 知识库背景（KB Agent 摘要）
  {kb_summary}
+ ## 历史相似事件（History Agent 摘要）
  {incident_history_summary}
+ ## 相关 Runbook（Runbook Agent 摘要）
  {runbook_summary}
+ ## 推荐排查方法论（匹配的 Skills）
  {matched_skills 精简内容}
```

### 11.5 预设 Skills 列表

| Skill | 标签 | 适用服务类型 |
|-------|------|-------------|
| MySQL 故障排查 | mysql, database, slow_query, connection | mysql |
| Redis 内存分析 | redis, memory, eviction, oom | redis |
| PostgreSQL 排查 | postgresql, vacuum, lock, replication | postgresql |
| K8s Pod CrashLoopBackOff | k8s, crashloop, oom, pod | k8s_deployment, k8s_statefulset |
| Linux 内存 OOM | linux, oom, memory, kill | (所有 SSH) |
| 网络连通性排查 | network, timeout, dns, connection_refused | (通用) |
| Cron Job 故障 | cron, scheduled, timer | cron_job, systemd |
| Nginx 排查 | nginx, 502, 504, upstream | nginx |

---

## 十二、定时任务

### 12.1 Incident History → Runbook 聚合

每天凌晨 2:00，将最近新增的 incident_history 整合到对应的 Runbook 中：

```
1. 获取昨天 saved_to_memory=true 的 incidents
2. 对每个 incident：
   a. 按 tags 匹配已有 Runbook
   b. 如果有匹配 → LLM 将新 incident 经验合并进现有 Runbook
   c. 如果无匹配 → LLM 根据 incident 生成新 Runbook（draft 状态）
3. 重新生成更新后 Runbook 的 embedding
```

这是系统的学习闭环：事件解决 → 保存历史 → 聚合成 Runbook → 指导未来排查。

---

## 十三、前端页面结构

### 13.1 技术栈

React 19 + TanStack Router + Vite + shadcn/ui + Tailwind CSS + TanStack Query + ofetch + Zustand + Streamdown + Motion + pnpm

### 13.2 页面列表

| 路径 | 页面 | 功能 |
|------|------|------|
| `/` | Inbox | 事件列表表格，状态筛选，每行可进入详情 |
| `/incidents/:id` | 事件详情 | SSE 对话流 + 审批卡片 + 用户输入框 |
| `/infrastructure` | Infrastructure | 基础设施 + 服务的树形管理 |
| `/projects` | Projects | 知识库项目 CRUD |
| `/projects/:id` | 项目详情 | cloud.md 编辑 + 文档上传 + 服务关联 |
| `/runbooks` | Runbooks | Runbook 列表 + Markdown 编辑 |
| `/skills` | Skills | Skill 列表 + Markdown 编辑（预设 + 自定义） |
| `/settings` | Settings | Webhook 配置 + LLM 配置 |

### 13.3 事件详情页 — 多 Agent 阶段展示

事件详情页根据 SSE 事件的 `phase` 和 `agent` 字段，分三个阶段展示 Agent 的执行过程：

#### 阶段一：gather_context（Sub Agent 并行 — 卡片网格）

```
┌─────────────────────────────────────────────┐
│  📋 正在收集上下文...                          │
│                                              │
│  ┌──────────────────┐  ┌──────────────────┐  │
│  │ 📚 知识库 Agent   │  │ 📖 历史事件 Agent │  │
│  │ ● 检索中...       │  │ ● 检索中...       │  │
│  │ → search_knowledge│  │ → search_incident │  │
│  │   query: "活动报告"│  │   query: "数据不更新"│
│  │ ✅ 找到 2 个相关项目│  │ ✅ 找到 1 个相似事件│  │
│  └──────────────────┘  └──────────────────┘  │
│  ┌──────────────────┐                        │
│  │ 📒 Runbook Agent  │                        │
│  │ ● 检索中...       │                        │
│  │ ✅ 匹配到 Cron 排查│                        │
│  └──────────────────┘                        │
│                                              │
│  ✅ 上下文收集完成                              │
└─────────────────────────────────────────────┘
```

设计要点：
- 3 个 Sub Agent 以**卡片网格（grid）**展示，体现并行
- 每个卡片显示：Agent 名称 + 状态（检索中/完成）+ 工具调用 + 摘要结果
- 工具调用细节**默认折叠**，点击展开
- 整个 gather_context 阶段用一个**可折叠容器**包裹，完成后自动折叠为一行摘要

#### 阶段二：main_agent（主排查流程 — 单列时间线）

```
┌─────────────────────────────────────────────┐
│  🤖 主 Agent                                 │
│                                              │
│  💭 分析事件内容，活动报告数据截止到1月18日...    │
│                                              │
│  🔍 假设 1: 定时同步任务停止运行                 │
│  ┌─ 🛠️ exec_read ──────────────────────────┐│
│  │ infra: prod-server-01                    ││
│  │ $ crontab -l | grep sync                ││
│  │ ─────────────────────────────            ││
│  │ 输出:                                    ││
│  │ 0 2 * * * /opt/scripts/sync-job.sh       ││
│  └──────────────────────────────────────────┘│
│                                              │
│  ┌─ 🛠️ exec_read ──────────────────────────┐│
│  │ infra: prod-server-01                    ││
│  │ $ journalctl -u sync-job --since "2026-01││
│  │ ─────────────────────────────            ││
│  │ 输出:                                    ││
│  │ Jan 18 03:14:22 OOM killer invoked...    ││
│  └──────────────────────────────────────────┘│
│                                              │
│  📊 发现：sync-job 在 1月18日因 OOM 被 kill    │
│  ✅ 假设 1 确认                                │
│                                              │
│  ⚠️ 申请执行写操作                             │
│  ┌─ 审批卡片 ───────────────────────────────┐│
│  │ 🛠️ exec_write                           ││
│  │ $ systemctl restart sync-job             ││
│  │ 风险: MEDIUM | 回滚: systemctl stop ...  ││
│  │         [✅ 批准]  [❌ 拒绝]              ││
│  └──────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
```

设计要点：
- 主 Agent 的思考用**对话气泡**展示，流式 Markdown（Streamdown）
- 工具调用用**代码卡片**展示：工具名 + 参数 + 输出
- 工具输出**默认展开**（主 Agent 的工具输出是排查过程核心，用户需要看到）
- 审批用**醒目卡片**，有操作按钮
- 整体是**单列时间线**布局

#### 阶段三：summarize（事件报告）

```
┌─────────────────────────────────────────────┐
│  📝 事件报告                                  │
│  ────────────────────────────────            │
│  [Markdown 渲染的完整报告]                     │
│  ────────────────────────────────            │
│  [💾 保存到历史]  [📋 复制]                     │
└─────────────────────────────────────────────┘
```

### 13.4 SSE 事件渲染逻辑

```typescript
function handleSSEEvent(event: SSEEvent) {
  // 阶段切换
  if (event.type === "phase_change") {
    setCurrentPhase(event.phase)
    return
  }

  // 按 phase 分发到不同区域
  switch (event.phase) {
    case "gather_context":
      // 更新对应 agent 的 SubAgentCard
      updateSubAgentCard(event.agent, event)
      break
    case "main_agent":
      // 追加到主 Agent 时间线
      appendToTimeline(event)
      break
    case "summarize":
      // 渲染最终报告
      renderSummary(event)
      break
  }
}
```

### 13.5 前端组件结构

```
<IncidentDetailPage>
  <EventTimeline>
    <!-- phase: gather_context -->
    <GatherContextSection collapsed={isComplete}>
      <SubAgentCard agent="kb" />
      <SubAgentCard agent="history" />
      <SubAgentCard agent="runbook" />
    </GatherContextSection>

    <!-- phase: main_agent -->
    <MainAgentSection>
      <ThinkingBubble />      <!-- type: thinking -->
      <ToolCallCard />        <!-- type: tool_start/end -->
      <ApprovalCard />        <!-- type: approval_required -->
      ...repeat...
    </MainAgentSection>

    <!-- phase: summarize -->
    <SummarySection>
      <MarkdownReport />
    </SummarySection>
  </EventTimeline>

  <UserInputBar />  <!-- 用户追加消息 -->
</IncidentDetailPage>
```

### 13.6 Infrastructure 页面树形结构

```
Infrastructure
├── [+ 添加服务器]  [+ 添加 K8s 集群]
│
├── 🖥️ prod-server-01  (192.168.1.10)  [SSH]  ● 已连接
│   ├── 🐬 MySQL 8.0       localhost:3306      ● 健康
│   ├── 🔴 Redis 7          localhost:6379      ● 健康
│   ├── ⏰ sync-job         crontab             ● 运行中
│   ├── 🐳 nginx-proxy      docker container    ● 运行中
│   └── [+ 添加服务] [🔍 自动发现]
│
└── ☸️ k8s-cluster-prod  [K8s]                 ● 已连接
    ├── 📦 order-service    default/order-svc   ⚠️ 警告
    ├── 📦 payment-service  default/payment-svc ● 健康
    └── [+ 添加服务] [🔍 自动发现]
```

> Docker 容器作为 SSH 服务器上的服务管理，通过 `exec_read` 执行 `docker` CLI 命令操作。

添加服务时支持两种方式：
1. **手动添加** — 填写服务名、类型、业务上下文等
2. **自动发现** — 通过 `exec_read` 执行扫描命令（如 `systemctl list-units`、`docker ps`），解析结果后用户选择要保存的服务

### 13.7 Monitoring 配置（项目设置中）

在项目详情页的设置 Tab 中，支持配置监控源：

```
项目设置 > 监控源
┌─────────────────────────────────────────────┐
│  📊 监控源配置                                │
│                                              │
│  ┌─ Prometheus ────────────────────────────┐│
│  │ 名称: 生产环境 Prometheus                ││
│  │ 地址: http://prometheus.internal:9090   ││
│  │ 认证: Bearer Token  [••••••••]          ││
│  │ 状态: ● 已连接                           ││
│  │         [测试连接]  [删除]               ││
│  └──────────────────────────────────────────┘│
│                                              │
│  ┌─ Loki ──────────────────────────────────┐│
│  │ 名称: 生产环境 Loki                      ││
│  │ 地址: http://loki.internal:3100         ││
│  │ 认证: Basic Auth                        ││
│  │ 状态: ● 已连接                           ││
│  │         [测试连接]  [删除]               ││
│  └──────────────────────────────────────────┘│
│                                              │
│  [+ 添加监控源]                               │
└─────────────────────────────────────────────┘
```

配置项：
- **类型**：Prometheus / Loki
- **名称**：自定义名称，用于展示
- **Endpoint**：监控服务地址
- **认证方式**：无认证 / Bearer Token / Basic Auth（加密存储）
- **连接测试**：调用 Prometheus `/api/v1/status/buildinfo` 或 Loki `/ready` 验证

---

## 十四、安全策略

### 14.1 连接凭证安全

- conn_config 字段使用 Fernet 对称加密后存储为 BYTEA
- 加密密钥从环境变量 `ENCRYPTION_KEY` 读取
- API 返回时不包含 conn_config 明文，只返回连接状态
- SSH Key / kubeconfig / 密码全部在 conn_config 中加密

### 14.2 命令安全 — exec_read 白名单

```python
# 只读命令白名单（前缀匹配）
READ_COMMAND_WHITELIST = [
    "cat", "head", "tail", "less", "grep", "awk", "sed -n",
    "ls", "find", "stat", "file", "wc",
    "ps", "top", "htop", "free", "df", "du", "uptime", "w", "vmstat", "iostat",
    "ss", "netstat", "ip", "ping", "traceroute", "dig", "nslookup", "curl",
    "systemctl status", "systemctl list", "systemctl show",
    "journalctl",
    "crontab -l", "at -l",
    "docker ps", "docker inspect", "docker logs", "docker stats", "docker top",
    "kubectl get", "kubectl describe", "kubectl logs", "kubectl top",
    "mysql -e", "mysql -u", "psql -c", "psql -U", "redis-cli",
]

# 绝对禁止（即使在 exec_write 中也拦截）
BLOCKED_PATTERNS = [
    "rm -rf /", "dd if=/dev/zero", "mkfs", "> /dev/sd",
    ":(){ :|:& };:",  # fork bomb
    "chmod -R 777 /", "chown -R",
]
```

### 14.3 其他安全措施

1. **Webhook 签名验证** — HMAC-SHA256，防止伪造事件
2. **SSE 身份验证** — JWT token 验证
3. **审计日志** — 所有写操作记录到 approval_requests，包含操作者和时间
4. **网络隔离** — Agent 容器只允许访问已注册的 Infrastructure IP
5. **输出限制** — 命令输出限制 4000 字符，超出自动压缩（头+尾+LLM 摘要）
6. **超时控制** — SSH 命令 30s，HTTP 请求 10s，K8s API 15s

---

## 十五、环境变量

```bash
# .env
DATABASE_URL=postgresql+asyncpg://ops_agent:password@localhost:5432/ops_agent
REDIS_URL=redis://localhost:6379/0

# LLM
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1    # 可配置代理
MAIN_MODEL=gpt-4o                             # 主 Agent 模型
MINI_MODEL=gpt-4o-mini                        # Sub Agent 模型

# 加密
ENCRYPTION_KEY=...                            # Fernet key，用于 conn_config 加密

# LangGraph Checkpoint
LANGGRAPH_CHECKPOINT_DSN=postgresql://ops_agent:password@localhost:5432/ops_agent

# 密钥挂载（可选，用于 K8s 部署）
SSH_KEYS_DIR=/secrets/ssh-keys
KUBECONFIG_DIR=/secrets/kubeconfigs

# Webhook
WEBHOOK_SECRET=...                            # HMAC-SHA256 签名密钥

# JWT
JWT_SECRET=...
```

---

## 十六、API 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/incidents` | 事件列表（分页、筛选） |
| POST | `/api/incidents` | 创建事件（手动触发） |
| GET | `/api/incidents/:id` | 事件详情 |
| PATCH | `/api/incidents/:id` | 更新事件（状态、保存到记忆） |
| GET | `/api/incidents/:id/stream` | SSE 流式推送 |
| POST | `/api/incidents/:id/chat` | 用户在事件中追加消息 |
| GET | `/api/incidents/:id/messages` | 事件对话历史 |
| POST | `/api/approvals/:id/decide` | 审批决定（approve/reject） |
| GET | `/api/infrastructures` | 基础设施列表 |
| POST | `/api/infrastructures` | 添加基础设施 |
| PUT | `/api/infrastructures/:id` | 更新基础设施 |
| DELETE | `/api/infrastructures/:id` | 删除基础设施 |
| POST | `/api/infrastructures/:id/test` | 测试连接 |
| POST | `/api/infrastructures/:id/discover` | 自动发现服务 |
| GET | `/api/services` | 服务列表 |
| POST | `/api/services` | 添加服务 |
| PUT | `/api/services/:id` | 更新服务 |
| DELETE | `/api/services/:id` | 删除服务 |
| GET | `/api/projects` | 项目列表 |
| POST | `/api/projects` | 创建项目 |
| GET | `/api/projects/:id` | 项目详情 |
| PUT | `/api/projects/:id` | 更新项目（含 cloud.md） |
| DELETE | `/api/projects/:id` | 删除项目 |
| POST | `/api/projects/:id/documents` | 上传文档 |
| GET | `/api/projects/:id/services` | 项目关联服务 |
| GET | `/api/projects/:id/dependencies` | 服务依赖图 |
| GET | `/api/runbooks` | Runbook 列表 |
| POST | `/api/runbooks` | 创建 Runbook |
| PUT | `/api/runbooks/:id` | 更新 Runbook |
| DELETE | `/api/runbooks/:id` | 删除 Runbook |
| GET | `/api/skills` | Skill 列表 |
| POST | `/api/skills` | 创建 Skill |
| PUT | `/api/skills/:id` | 更新 Skill |
| DELETE | `/api/skills/:id` | 删除 Skill（预设不可删） |
| POST | `/api/webhooks/alert` | Webhook 接收告警 |
| POST | `/api/upload` | 文件上传（截图等） |
| GET | `/health` | 健康检查 |

---

## 十七、验证方案

新项目搭建后，按以下场景逐步验证：

| # | 场景 | 验证能力 |
|---|------|---------|
| 1 | 添加 SSH 服务器 → exec_read 测试连接 | 连接 + 基础命令执行 |
| 2 | exec_read 执行 mysql -e 查询 | 数据库查询走 CLI |
| 3 | exec_read 获取日志 → Agent 分析异常 | 日志采集 + 分析 |
| 4 | exec_write 触发审批 → 前端审批卡片 | 审批流程端到端 |
| 5 | 提交"活动报告不更新"事件 → Agent 全流程排查 | 端到端场景（见下方） |
| 6 | 事件解决 → 保存历史 → 定时任务更新 Runbook | 学习闭环 |

### 端到端场景：活动报告 1 月之后不更新

```
1. 用户提交截图 + 描述
2. gather_context（前端展示 3 个 Sub Agent 卡片网格）:
   - KB Agent → search_knowledge_base → 定位"KFC 企划分析系统"项目
   - History Agent → search_incident_history → 查找相似事件
   - Runbook Agent → search_runbook → 匹配 Cron Job 故障 Skill
3. main_agent（前端展示时间线）:
   - search_knowledge_base → 了解项目架构和服务依赖
   - exec_read(infra_id, 'crontab -l | grep sync') → 找到 sync-job
   - exec_read(infra_id, 'journalctl -u sync-job --since "2026-01-18" | tail -100') → OOM killed
   - exec_read(infra_id, 'free -m') → 内存 95%
   - exec_read(infra_id, 'mysql -e "SELECT MAX(activity_date) FROM activity_reports"') → 2026-01-18
   - 确认根因：sync-job OOM 后未自动恢复
4. 申请写操作 → exec_write(infra_id, 'systemctl restart sync-job', ...) → 审批
5. 审批通过 → 执行重启
6. 验证 → exec_read 确认 crontab + 数据库最新日期
7. summarize → 生成事件报告
```
```
