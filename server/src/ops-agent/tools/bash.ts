import { z } from "zod";
import type { ToolDefinition, PermissionResult } from "../types";
import { classifyShellCommand } from "../safety/shell-classifier";
import { toPermissionResult } from "../safety/permissions";

const MAX_TIMEOUT = 300; // 5 分钟

const schema = z.object({
  command: z.string().describe("要执行的 Shell 命令"),
  timeout: z
    .number()
    .optional()
    .default(30)
    .describe("命令超时时间（秒），默认 30，最大 300"),
});

type BashArgs = z.infer<typeof schema>;

export const bashTool: ToolDefinition<BashArgs> = {
  name: "bash",
  description: `在本地执行 Shell 命令。用于运维排查中需要的系统命令、文件查看、进程检查、网络诊断等。
注意事项：
- 只读命令（ls, cat, ps, docker ps, kubectl get 等）自动放行
- 写操作（sed -i, curl POST, mv 等）需要审批
- 危险操作（rm -rf, kill -9 等）需要高级审批
- 灾难性命令（rm -rf /, fork bomb 等）会被直接拒绝
- 优先使用 service_exec 操作已注册的 Docker/K8s/DB 服务`,
  parameters: schema,
  needsPermissionCheck: true,
  maxResultChars: 30_000,

  async checkPermission(args): Promise<PermissionResult> {
    const commandType = classifyShellCommand(args.command);
    return toPermissionResult(commandType, `Shell 命令: ${args.command}`);
  },

  async execute(args) {
    const timeoutSec = Math.min(args.timeout ?? 30, MAX_TIMEOUT);

    const proc = Bun.spawn(["bash", "-c", args.command], {
      stdout: "pipe",
      stderr: "pipe",
      env: { ...process.env, LC_ALL: "en_US.UTF-8" },
    });

    const timer = setTimeout(() => proc.kill(), timeoutSec * 1000);

    try {
      const [stdout, stderr] = await Promise.all([
        new Response(proc.stdout).text(),
        new Response(proc.stderr).text(),
      ]);
      const exitCode = await proc.exited;

      clearTimeout(timer);

      const parts: string[] = [];
      if (stdout) parts.push(stdout);
      if (stderr) parts.push(`[STDERR]\n${stderr}`);
      if (exitCode !== 0) parts.push(`[EXIT CODE] ${exitCode}`);

      return parts.join("\n") || "(no output)";
    } catch (err) {
      clearTimeout(timer);
      throw err;
    }
  },
};
