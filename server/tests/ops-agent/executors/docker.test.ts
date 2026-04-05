import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import Docker from "dockerode";
import { dockerExecutor } from "@/ops-agent/executors/docker";
import { executeService } from "@/ops-agent/executors/registry";
import { removeContainerIfExists, insertServiceRecord } from "./helpers";

const DOCKER_SOCKET = "/var/run/docker.sock";
const CONTAINER_NAME = "chronos-exec-test-nginx";
const CONTAINER_PORT = "28080";

const docker = new Docker({ socketPath: DOCKER_SOCKET });

const connInfo: Record<string, unknown> = {
  socketPath: DOCKER_SOCKET,
};

let containerId: string;

describe("Docker Executor", () => {
  beforeAll(async () => {
    await removeContainerIfExists(docker, CONTAINER_NAME);

    const container = await docker.createContainer({
      Image: "nginx:alpine",
      name: CONTAINER_NAME,
      HostConfig: {
        PortBindings: { "80/tcp": [{ HostPort: CONTAINER_PORT }] },
      },
    });
    await container.start();

    const info = await container.inspect();
    containerId = info.Id;

    // 等待容器启动
    await Bun.sleep(2000);
  }, 30_000);

  afterAll(async () => {
    await removeContainerIfExists(docker, CONTAINER_NAME);
  });

  // ── 读操作 ──────────────────────────────────────────

  describe("读操作", () => {
    it("listContainers 包含测试容器", async () => {
      const containers = (await dockerExecutor(connInfo, "listContainers", {})) as Array<{
        Names: string[];
        State: string;
      }>;
      const found = containers.find((c) =>
        c.Names.some((n: string) => n.includes(CONTAINER_NAME)),
      );
      expect(found).toBeDefined();
      expect(found!.State).toBe("running");
    });

    it("inspectContainer 返回容器详情", async () => {
      const info = (await dockerExecutor(connInfo, "inspectContainer", {
        containerId,
      })) as {
        Id: string;
        State: { Running: boolean };
        Config: { Image: string };
      };
      expect(info.Id).toBe(containerId);
      expect(info.State.Running).toBe(true);
      expect(info.Config.Image).toBe("nginx:alpine");
    });

    it("containerLogs 返回日志字符串", async () => {
      const logs = await dockerExecutor(connInfo, "containerLogs", {
        containerId,
        tail: 10,
      });
      expect(typeof logs).toBe("string");
    });

    it("containerTop 返回进程列表", async () => {
      const top = (await dockerExecutor(connInfo, "containerTop", {
        containerId,
      })) as { Processes: string[][] };
      expect(top.Processes).toBeDefined();
      expect(Array.isArray(top.Processes)).toBe(true);
    });

    it("containerStats 返回资源统计", async () => {
      const stats = (await dockerExecutor(connInfo, "containerStats", {
        containerId,
      })) as Record<string, unknown>;
      expect(stats.cpu_stats).toBeDefined();
      expect(stats.memory_stats).toBeDefined();
    });

    it("listImages 返回镜像列表", async () => {
      const images = (await dockerExecutor(connInfo, "listImages", {})) as Array<Record<string, unknown>>;
      expect(images.length).toBeGreaterThan(0);
    });

    it("listNetworks 包含 bridge 网络", async () => {
      const networks = (await dockerExecutor(connInfo, "listNetworks", {})) as Array<{
        Name: string;
      }>;
      const bridge = networks.find((n) => n.Name === "bridge");
      expect(bridge).toBeDefined();
    });

    it("listVolumes 返回卷列表", async () => {
      const result = (await dockerExecutor(connInfo, "listVolumes", {})) as {
        Volumes: unknown[];
      };
      expect(result.Volumes).toBeDefined();
      expect(Array.isArray(result.Volumes)).toBe(true);
    });

    it("systemInfo 返回系统信息", async () => {
      const info = (await dockerExecutor(connInfo, "systemInfo", {})) as Record<string, unknown>;
      expect(info.Containers).toBeDefined();
      expect(info.Images).toBeDefined();
    });

    it("systemDf 返回磁盘使用情况", async () => {
      const df = (await dockerExecutor(connInfo, "systemDf", {})) as Record<string, unknown>;
      expect(df.Images).toBeDefined();
      expect(df.Containers).toBeDefined();
    });
  });

  // ── 生命周期操作 ────────────────────────────────────

  describe("生命周期操作", () => {
    it("stopContainer → startContainer 正常切换", async () => {
      // 停止
      await dockerExecutor(connInfo, "stopContainer", { containerId });
      let info = (await dockerExecutor(connInfo, "inspectContainer", { containerId })) as {
        State: { Running: boolean };
      };
      expect(info.State.Running).toBe(false);

      // 启动
      await dockerExecutor(connInfo, "startContainer", { containerId });
      info = (await dockerExecutor(connInfo, "inspectContainer", { containerId })) as {
        State: { Running: boolean };
      };
      expect(info.State.Running).toBe(true);
    });

    it("restartContainer 重启容器", async () => {
      const beforeInfo = (await dockerExecutor(connInfo, "inspectContainer", { containerId })) as {
        State: { StartedAt: string; Running: boolean };
      };
      const beforeStarted = beforeInfo.State.StartedAt;

      await dockerExecutor(connInfo, "restartContainer", { containerId });

      const afterInfo = (await dockerExecutor(connInfo, "inspectContainer", { containerId })) as {
        State: { StartedAt: string; Running: boolean };
      };
      expect(afterInfo.State.Running).toBe(true);
      expect(afterInfo.State.StartedAt).not.toBe(beforeStarted);
    });

    it("pauseContainer + unpauseContainer", async () => {
      // 暂停
      await dockerExecutor(connInfo, "pauseContainer", { containerId });
      let info = (await dockerExecutor(connInfo, "inspectContainer", { containerId })) as {
        State: { Paused: boolean };
      };
      expect(info.State.Paused).toBe(true);

      // 恢复
      await dockerExecutor(connInfo, "unpauseContainer", { containerId });
      info = (await dockerExecutor(connInfo, "inspectContainer", { containerId })) as {
        State: { Paused: boolean };
      };
      expect(info.State.Paused).toBe(false);
    });
  });

  // ── 危险操作 ────────────────────────────────────────

  describe("危险操作", () => {
    it("killContainer 终止容器", async () => {
      // 先创建一个临时容器用于 kill
      const tempName = "chronos-exec-test-kill-temp";
      await removeContainerIfExists(docker, tempName);
      const temp = await docker.createContainer({
        Image: "nginx:alpine",
        name: tempName,
      });
      await temp.start();
      const tempInfo = await temp.inspect();

      await dockerExecutor(connInfo, "killContainer", { containerId: tempInfo.Id });

      const info = await temp.inspect();
      expect(info.State.Running).toBe(false);

      await removeContainerIfExists(docker, tempName);
    });

    it("removeContainer 强制删除容器", async () => {
      const tempName = "chronos-exec-test-remove-temp";
      await removeContainerIfExists(docker, tempName);
      const temp = await docker.createContainer({
        Image: "nginx:alpine",
        name: tempName,
      });
      await temp.start();
      const tempInfo = await temp.inspect();

      await dockerExecutor(connInfo, "removeContainer", {
        containerId: tempInfo.Id,
        force: true,
      });

      // 验证容器已被删除
      try {
        await temp.inspect();
        // 不应到达这里
        expect(true).toBe(false);
      } catch (err: unknown) {
        expect((err as Error).message).toContain("no such container");
      }
    });
  });

  // ── executeService 注册流程 ──────────────────────────

  describe("executeService 端到端", () => {
    it("注册 Docker service + listContainers", async () => {
      const serviceId = await insertServiceRecord({
        name: "test-docker-exec",
        serviceType: "docker",
        host: "localhost",
        port: 2376,
        config: { socketPath: DOCKER_SOCKET },
      });

      const containers = (await executeService(serviceId, "listContainers", {})) as Array<{
        Names: string[];
      }>;
      const found = containers.find((c) =>
        c.Names.some((n: string) => n.includes(CONTAINER_NAME)),
      );
      expect(found).toBeDefined();
    });
  });

  // ── 错误处理 ──────────────────────────────────────────

  describe("错误处理", () => {
    it("不存在的容器 ID 报错", async () => {
      await expect(
        dockerExecutor(connInfo, "inspectContainer", { containerId: "nonexistent_container_id" }),
      ).rejects.toThrow();
    });

    it("不支持的 operation 报错", async () => {
      await expect(dockerExecutor(connInfo, "unknownOp", {})).rejects.toThrow(
        'unsupported operation "unknownOp"',
      );
    });
  });
});
