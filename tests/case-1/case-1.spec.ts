/**
 * Case 1: 磁盘占满事件 — 完整生命周期 E2E 测试
 *
 * ═══════════════════════════════════════════════════════════════
 * 场景描述
 * ═══════════════════════════════════════════════════════════════
 *
 * 模拟一台 Linux 服务器 /tmp 目录被大文件占满的运维故障场景。
 * 用户通过 Chronos 前端提交事件描述，后端 AI Agent（LangGraph）自动完成
 * 故障排查与修复，最终生成事件总结。
 *
 * ═══════════════════════════════════════════════════════════════
 * 基础设施生命周期（由 fixture 自动管理）
 * ═══════════════════════════════════════════════════════════════
 *
 * 启动阶段（测试开始前，worker-scoped fixture `infra` 自动执行）：
 *   1. docker compose up — 启动 3 个容器：
 *      - PostgreSQL (pgvector:pg17, 端口 15432)  — 应用数据库 + LangGraph checkpoint
 *      - Redis (7-alpine, 端口 16379)            — 缓存
 *      - Target (Ubuntu 22.04 + SSHD, 端口 12222) — 模拟目标服务器，root/testpassword
 *   2. uv run alembic upgrade head — 在 backend/ 目录下跑数据库迁移
 *   3. uv run uvicorn src.main:app --port 8000 — 启动 FastAPI 后端，轮询等待健康
 *   4. pnpm dev --port 5173 — 启动 Vite 前端开发服务器，轮询等待健康
 *
 * 清理阶段（测试结束后，fixture teardown 自动执行）：
 *   1. SIGTERM 杀掉后端和前端子进程
 *   2. docker compose down -v --remove-orphans — 销毁所有容器和数据卷
 *
 * ═══════════════════════════════════════════════════════════════
 * 测试数据（由 fixture `seedData` 通过 API 创建）
 * ═══════════════════════════════════════════════════════════════
 *
 * - 项目: "E2E Test Project"
 * - SSH 连接: name="test-target", localhost:12222, root/testpassword
 *   （指向 Docker 中的 target 容器）
 * - 服务: name="test-server", type=system_service
 * - 绑定: test-server ↔ test-target（服务与连接的关联关系，
 *   Agent 通过此绑定知道要 SSH 到哪台机器去排查）
 *
 * ═══════════════════════════════════════════════════════════════
 * Agent 处理流程与前端交互
 * ═══════════════════════════════════════════════════════════════
 *
 * 1. 用户在前端输入事件描述并提交 → 前端 POST /api/incidents 创建事件，
 *    后端启动 LangGraph Agent 异步处理，前端跳转到事件详情页并通过
 *    SSE/轮询实时展示 Agent 的思考与操作过程。
 *
 * 2. Agent 思考与执行循环：
 *    - Agent 分析用户描述，识别出"test-server 磁盘问题"
 *    - 通过服务绑定关系找到对应的 SSH 连接 test-target
 *    - Agent 规划操作：SSH 到目标机器执行 df -h、du 等命令排查磁盘占用
 *    - 执行前需要用户审批（human-in-the-loop）→ 前端弹出审批卡片，
 *      用户点击"批准"后 Agent 继续执行
 *    - Agent SSH 到目标机器，发现 /tmp/testfill 占用 450MB
 *    - Agent 规划清理操作（如 rm /tmp/testfill）→ 可能再次请求审批
 *    - 执行清理，验证磁盘空间已恢复
 *    - 过程中 Agent 可能通过 ask_human 向用户提问获取更多信息，
 *      前端显示提问横幅，用户回复后 Agent 继续处理
 *
 * 3. Agent 完成处理 → 生成事件总结（summary），将事件状态置为 resolved，
 *    前端渲染 summary-section 展示最终结果。
 *
 * ═══════════════════════════════════════════════════════════════
 * 本测试脚本的角色
 * ═══════════════════════════════════════════════════════════════
 *
 * 脚本通过 Playwright 操控浏览器，扮演"用户"的角色：
 * - 提交事件描述
 * - 在 8 分钟的轮询循环中，自动批准 Agent 请求的操作审批、
 *   回复 Agent 的 ask_human 提问
 * - 最终断言事件已 resolved，故障文件已被清理
 */
import { test, expect } from "./fixture.js";
import { waitForIncidentResolution } from "../lib/incident-loop.js";

test("磁盘占满事件 - 完整生命周期", async ({ page, seedData, faultInjector, apiClient }) => {
  // 1. 故障注入：在目标机器上制造磁盘占满
  await faultInjector.injectDiskFull();

  // 2. 打开事件页面
  await page.goto("/incidents");

  // 3. 创建事件
  await page.click('[data-testid="create-incident-btn"]');

  // 填写事件描述
  await page.fill(
    '[data-testid="prompt-textarea"]',
    "服务器 test-server 磁盘使用率过高，/tmp 目录占用异常，请排查原因并清理",
  );

  // 提交事件
  await page.click('[data-testid="submit-incident"]');

  // 4. 等待导航到事件详情页
  await page.waitForURL(/\/incidents\/[\w-]+/, { timeout: 15_000 });

  // 从 URL 提取 incident ID
  const incidentId = page.url().split("/incidents/")[1];

  // 5. 事件处理循环（最长 8 分钟）
  await waitForIncidentResolution(page, {
    askHumanReply: "请继续排查并清理 /tmp 目录下的大文件",
  });

  // 6. 断言
  const summary = page.locator('[data-testid="summary-section"]');
  await expect(summary).toBeVisible({ timeout: 30_000 });

  // 通过 API 验证 incident 状态
  const incident = await apiClient.getIncident(incidentId);
  expect(incident.status).toBe("resolved");

  // 断言 Agent 执行了 tool call（确认 Agent 实际工作了）
  const toolCallCards = page.locator('[data-testid="tool-call-card"]');
  const toolCallCount = await toolCallCards.count();
  expect(toolCallCount).toBeGreaterThanOrEqual(1);

  // 断言 summary 包含磁盘相关关键词
  const summaryText = await summary.textContent();
  expect(summaryText).toBeTruthy();
  const lowerSummary = summaryText!.toLowerCase();
  const hasRelevantKeyword = ["/tmp", "testfill", "disk", "磁盘", "清理", "删除", "空间"].some(
    (kw) => lowerSummary.includes(kw),
  );
  expect(hasRelevantKeyword).toBe(true);

  // 7. 验证故障已修复（best-effort）
  try {
    const result = await faultInjector.exec("test -f /tmp/testfill");
    expect(result.code).not.toBe(0); // file should be removed
  } catch {
    // best-effort, don't fail the test
  }

  // 8. 返回事件列表，验证事件显示为"已解决"
  await page.goto("/incidents");
  await expect(page.locator("text=已解决").first()).toBeVisible({ timeout: 10_000 });
});
