# E2E 测试指南

## 前提条件

- Docker & Docker Compose
- pnpm
- uv (Python 包管理)
- `DASHSCOPE_API_KEY` 环境变量（千问 API）

## 端口使用

| 服务 | 端口 |
|------|------|
| PostgreSQL | 5432 |
| Redis | 6379 |
| SSH Target | 2222 |
| Backend (FastAPI) | 8000 |
| Frontend (Vite) | 5173 |

确保以上端口未被占用。

## 一键启动

```bash
# 1. 启动基础设施（postgres + redis + ssh-target）
docker compose -f docker-compose.e2e.yml up -d --build

# 2. 等待所有容器健康
docker compose -f docker-compose.e2e.yml ps

# 3. 验证 SSH 可连接
ssh testuser@localhost -p 2222
# 密码: testpass

# 4. 启动后端
cd ops-agent
uv run alembic upgrade head
uv run uvicorn src.main:app --reload --port 8000

# 5. 启动前端（另一个终端）
cd web
pnpm dev

# 6. 运行自动化测试（另一个终端）
cd web
pnpm e2e:real
```

## 手动测试流程

### Step 1: 添加基础设施

1. 打开 http://localhost:5173/infrastructure
2. 点击 **Add Infrastructure**
3. 填写表单：
   - Name: `E2E Test Server`
   - Host: `localhost`
   - Port: `2222`
   - Username: `testuser`
   - Password: `testpass`
4. 点击 **Add**
5. 看到 toast 提示 "Infrastructure added"

### Step 2: 创建事件

1. 打开 http://localhost:5173/incidents
2. 点击 **创建事件** 按钮
3. 输入描述：`服务器磁盘空间告警，请检查磁盘使用情况`
4. 点击提交
5. 自动跳转到事件详情页

### Step 3: 观察 Agent

1. 等待事件时间线出现
2. 观察 Agent 执行过程：
   - `gather_context` 子 Agent 卡片出现
   - `list_infrastructures` 工具调用（发现可用基础设施）
   - `exec_read_tool` 工具调用（在服务器上执行 `df -h` 等诊断命令）
3. 等待总结报告出现

### Step 4: 验证结果

- 总结报告应包含磁盘使用情况的分析
- 应至少有 4 个工具调用卡片
- Agent 应自主发现并使用了 SSH 基础设施（无需手动指定）

## 自动化测试

```bash
# 运行 real-e2e 测试（带浏览器窗口）
cd web && pnpm e2e:real

# 无头模式
cd web && npx playwright test --project=real-e2e
```

测试录像和截图保存在 `web/test-results/` 目录下。

## 清理

```bash
# 停止并删除所有容器和数据
docker compose -f docker-compose.e2e.yml down -v
```

## 故障排除

### SSH 连接失败

```bash
# 检查容器状态
docker compose -f docker-compose.e2e.yml ps

# 查看 SSH 容器日志
docker compose -f docker-compose.e2e.yml logs ssh-target

# 手动测试
ssh -o StrictHostKeyChecking=no testuser@localhost -p 2222
```

### 端口冲突

如果端口被占用，先停止占用的服务：

```bash
# 查看端口占用
lsof -i :5432
lsof -i :6379
lsof -i :2222
```

### Agent 超时

- real-e2e 测试超时为 180 秒
- 如果 Agent 响应慢，检查 `DASHSCOPE_API_KEY` 是否有效
- 确保后端日志中没有 API 错误

### 容器中 systemctl 不可用

SSH 容器没有 systemd，`systemctl` 命令会失败。Agent 会自动适应，使用 `service`、`ps` 等替代命令。
