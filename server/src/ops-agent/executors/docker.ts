import Docker from "dockerode";
import type { Executor } from "../types";

export const dockerExecutor: Executor = async (conn, operation, params) => {
  // socketPath 优先：如果配置了 socketPath，忽略 host/port
  const dockerOpts = conn.socketPath
    ? { socketPath: conn.socketPath as string }
    : {
        host: (conn.host as string) || "localhost",
        port: (conn.port as number) || 2376,
        ...(conn.ca ? { ca: Buffer.from(conn.ca as string, "base64") } : {}),
        ...(conn.cert ? { cert: Buffer.from(conn.cert as string, "base64") } : {}),
        ...(conn.key ? { key: Buffer.from(conn.key as string, "base64") } : {}),
      };
  const docker = new Docker(dockerOpts);

  const handlers: Record<string, () => Promise<unknown>> = {
    // ── Read ──
    listContainers: () => docker.listContainers({ all: (params.all as boolean) ?? true }),
    inspectContainer: () => docker.getContainer(params.containerId as string).inspect(),
    containerLogs: async () => {
      const logs = await docker.getContainer(params.containerId as string).logs({
        stdout: true,
        stderr: true,
        tail: (params.tail as number) ?? 100,
        timestamps: (params.timestamps as boolean) ?? false,
      });
      return typeof logs === "string" ? logs : logs.toString("utf-8");
    },
    containerTop: () => docker.getContainer(params.containerId as string).top(),
    containerStats: () =>
      docker.getContainer(params.containerId as string).stats({ stream: false }),
    listImages: () => docker.listImages(),
    listNetworks: () => docker.listNetworks(),
    listVolumes: () => docker.listVolumes(),
    systemInfo: () => docker.info(),
    systemDf: () => docker.df(),

    // ── Write ──
    startContainer: () => docker.getContainer(params.containerId as string).start(),
    stopContainer: () => docker.getContainer(params.containerId as string).stop(),
    restartContainer: () => docker.getContainer(params.containerId as string).restart(),
    pauseContainer: () => docker.getContainer(params.containerId as string).pause(),
    unpauseContainer: () => docker.getContainer(params.containerId as string).unpause(),
    pullImage: () => docker.pull(params.image as string),

    // ── Dangerous ──
    removeContainer: () =>
      docker.getContainer(params.containerId as string).remove({ force: (params.force as boolean) ?? false }),
    removeImage: () => docker.getImage(params.image as string).remove(),
    killContainer: () => docker.getContainer(params.containerId as string).kill(),
  };

  const handler = handlers[operation];
  if (!handler) {
    throw new Error(
      `Docker: unsupported operation "${operation}". Available: ${Object.keys(handlers).join(", ")}`,
    );
  }

  return handler();
};
