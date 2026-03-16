import { type ChildProcess, execSync, spawn } from "child_process";
import { resolve } from "path";
import { loadEnv, requireEnv } from "./env.js";

const ROOT = resolve(import.meta.dirname, "../..");
const BACKEND_DIR = resolve(ROOT, "backend");
const WEB_DIR = resolve(ROOT, "web");

export class ProcessManager {
  private children: ChildProcess[] = [];

  private testEnv(): Record<string, string> {
    loadEnv();
    return {
      ...process.env as Record<string, string>,
      DATABASE_URL: "postgresql+asyncpg://chronos:chronos@localhost:15432/chronos",
      LANGGRAPH_CHECKPOINT_DSN: "postgresql://chronos:chronos@localhost:15432/chronos",
      REDIS_URL: "redis://localhost:16379/0",
      DASHSCOPE_API_KEY: requireEnv("DASHSCOPE_API_KEY"),
    };
  }

  runMigrations(): void {
    console.log("[proc] Running database migrations...");
    execSync("uv run alembic upgrade head", {
      cwd: BACKEND_DIR,
      env: this.testEnv(),
      stdio: "inherit",
      timeout: 60_000,
    });
    console.log("[proc] Migrations complete");
  }

  startBackend(): ChildProcess {
    console.log("[proc] Starting backend...");
    const child = spawn("uv", ["run", "uvicorn", "src.main:app", "--port", "8000"], {
      cwd: BACKEND_DIR,
      env: this.testEnv(),
      stdio: "pipe",
    });
    child.stdout?.on("data", (d) => process.stdout.write(`[backend] ${d}`));
    child.stderr?.on("data", (d) => process.stderr.write(`[backend] ${d}`));
    this.children.push(child);
    return child;
  }

  startFrontend(): ChildProcess {
    console.log("[proc] Starting frontend...");
    const child = spawn("pnpm", ["dev", "--port", "5173"], {
      cwd: WEB_DIR,
      env: process.env as Record<string, string>,
      stdio: "pipe",
    });
    child.stdout?.on("data", (d) => process.stdout.write(`[frontend] ${d}`));
    child.stderr?.on("data", (d) => process.stderr.write(`[frontend] ${d}`));
    this.children.push(child);
    return child;
  }

  stopAll(): void {
    console.log("[proc] Stopping all processes...");
    for (const child of this.children) {
      try {
        child.kill("SIGTERM");
      } catch {
        // already dead
      }
    }
    this.children = [];
  }
}
