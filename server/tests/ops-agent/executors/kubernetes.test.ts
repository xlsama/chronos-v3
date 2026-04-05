import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { execSync, spawn, type ChildProcess } from "node:child_process";
import { writeFileSync } from "node:fs";
import { k8sExecutor } from "@/ops-agent/executors/kubernetes";
import { executeService } from "@/ops-agent/executors/registry";
import { insertServiceRecord, waitForPort } from "./helpers";

const TEST_NS = "chronos-test-ns";
const DEPLOY_NAME = "nginx";
const SVC_NAME = "nginx-svc";
const REPLICAS = 2;
const PROXY_PORT = 28443;

let k8sAvailable = false;
let proxyProcess: ChildProcess | null = null;
let proxyKubeconfig: string;

// 生成指向 kubectl proxy 的 kubeconfig（无认证，纯 HTTP）
function makeProxyKubeconfig(port: number): string {
  return `
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: http://127.0.0.1:${port}
    insecure-skip-tls-verify: true
  name: proxy
contexts:
- context:
    cluster: proxy
    user: proxy
  name: proxy
current-context: proxy
users:
- name: proxy
  user: {}
`;
}

const connInfo: Record<string, unknown> = {};

describe("Kubernetes Executor", () => {
  beforeAll(async () => {
    // 检查 kubectl + 集群是否可用
    try {
      execSync("kubectl get nodes", { encoding: "utf-8", timeout: 10_000 });
      k8sAvailable = true;
    } catch {
      console.log("kubectl 不可用或集群未连通，跳过 Kubernetes 测试");
      return;
    }

    // 启动 kubectl proxy（处理 TLS 和认证，暴露无认证的 HTTP 端口）
    proxyProcess = spawn("kubectl", ["proxy", "--port", String(PROXY_PORT)], {
      stdio: "ignore",
    });

    // 等待 proxy 就绪
    await waitForPort(PROXY_PORT, "127.0.0.1", 10_000);

    // 生成指向 proxy 的 kubeconfig
    proxyKubeconfig = makeProxyKubeconfig(PROXY_PORT);
    connInfo.kubeconfig = proxyKubeconfig;

    // 创建测试 namespace
    try {
      execSync(`kubectl create namespace ${TEST_NS}`, {
        encoding: "utf-8",
        timeout: 10_000,
      });
    } catch {
      // already exists
    }

    // 部署 nginx deployment + service
    const deployYaml = `
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${DEPLOY_NAME}
  namespace: ${TEST_NS}
spec:
  replicas: ${REPLICAS}
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: ${SVC_NAME}
  namespace: ${TEST_NS}
spec:
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
`;
    const tmpYaml = `/tmp/chronos-k8s-test-${Date.now()}.yaml`;
    writeFileSync(tmpYaml, deployYaml);

    try {
      execSync(`kubectl apply -f ${tmpYaml}`, { encoding: "utf-8", timeout: 30_000 });
      execSync(
        `kubectl -n ${TEST_NS} rollout status deployment/${DEPLOY_NAME} --timeout=60s`,
        { encoding: "utf-8", timeout: 90_000 },
      );
    } finally {
      execSync(`rm -f ${tmpYaml}`);
    }
  }, 120_000);

  afterAll(async () => {
    // 停止 kubectl proxy
    if (proxyProcess) {
      proxyProcess.kill();
      proxyProcess = null;
    }
    if (!k8sAvailable) return;
    // 清理测试 namespace
    try {
      execSync(`kubectl delete namespace ${TEST_NS} --wait=false`, {
        encoding: "utf-8",
        timeout: 15_000,
      });
    } catch {
      // ignore
    }
  });

  // ── 读操作 ──────────────────────────────────────────

  describe("读操作", () => {
    it("listNamespaces 包含测试命名空间", async () => {
      if (!k8sAvailable) return;
      const namespaces = (await k8sExecutor(connInfo, "listNamespaces", {})) as string[];
      expect(namespaces).toContain("default");
      expect(namespaces).toContain(TEST_NS);
    });

    it("listPods 返回 nginx pods", async () => {
      if (!k8sAvailable) return;
      const pods = (await k8sExecutor(connInfo, "listPods", {
        namespace: TEST_NS,
      })) as Array<{ name: string; status: string; ready: boolean }>;
      expect(pods.length).toBe(REPLICAS);
      for (const pod of pods) {
        expect(pod.name).toContain(DEPLOY_NAME);
        expect(pod.status).toBe("Running");
        expect(pod.ready).toBe(true);
      }
    });

    it("describePod 返回 pod 详情", async () => {
      if (!k8sAvailable) return;
      const pods = (await k8sExecutor(connInfo, "listPods", {
        namespace: TEST_NS,
      })) as Array<{ name: string }>;

      const pod = (await k8sExecutor(connInfo, "describePod", {
        namespace: TEST_NS,
        name: pods[0].name,
      })) as { metadata: { name: string; namespace: string }; spec: unknown; status: unknown };

      expect(pod.metadata.name).toBe(pods[0].name);
      expect(pod.metadata.namespace).toBe(TEST_NS);
      expect(pod.spec).toBeDefined();
      expect(pod.status).toBeDefined();
    });

    it("getPodLogs 返回日志", async () => {
      if (!k8sAvailable) return;
      const pods = (await k8sExecutor(connInfo, "listPods", {
        namespace: TEST_NS,
      })) as Array<{ name: string }>;

      const logs = await k8sExecutor(connInfo, "getPodLogs", {
        namespace: TEST_NS,
        name: pods[0].name,
        tail: 10,
      });
      expect(typeof logs).toBe("string");
    });

    it("listDeployments 返回 nginx deployment", async () => {
      if (!k8sAvailable) return;
      const deployments = (await k8sExecutor(connInfo, "listDeployments", {
        namespace: TEST_NS,
      })) as Array<{ name: string; replicas: number; readyReplicas: number }>;

      expect(deployments.length).toBe(1);
      expect(deployments[0].name).toBe(DEPLOY_NAME);
      expect(deployments[0].replicas).toBe(REPLICAS);
      expect(deployments[0].readyReplicas).toBe(REPLICAS);
    });

    it("describeDeployment 返回详情", async () => {
      if (!k8sAvailable) return;
      const deploy = (await k8sExecutor(connInfo, "describeDeployment", {
        namespace: TEST_NS,
        name: DEPLOY_NAME,
      })) as { metadata: { name: string }; spec: { replicas: number } };

      expect(deploy.metadata.name).toBe(DEPLOY_NAME);
      expect(deploy.spec.replicas).toBe(REPLICAS);
    });

    it("listServices 返回 nginx service", async () => {
      if (!k8sAvailable) return;
      const svcs = (await k8sExecutor(connInfo, "listServices", {
        namespace: TEST_NS,
      })) as Array<{ name: string; type: string }>;

      const nginxSvc = svcs.find((s) => s.name === SVC_NAME);
      expect(nginxSvc).toBeDefined();
      expect(nginxSvc!.type).toBe("ClusterIP");
    });

    it("listNodes 返回至少 1 个 Ready 节点", async () => {
      if (!k8sAvailable) return;
      const nodes = (await k8sExecutor(connInfo, "listNodes", {})) as Array<{
        name: string;
        status: string;
      }>;
      expect(nodes.length).toBeGreaterThanOrEqual(1);
      expect(nodes.some((n) => n.status === "True")).toBe(true);
    });
  });

  // ── 写操作 ──────────────────────────────────────────

  describe("写操作", () => {
    it("scaleDeployment 扩容到 3", async () => {
      if (!k8sAvailable) return;
      const result = (await k8sExecutor(connInfo, "scaleDeployment", {
        namespace: TEST_NS,
        name: DEPLOY_NAME,
        replicas: 3,
      })) as { scaled: boolean; replicas: number };

      expect(result.scaled).toBe(true);
      expect(result.replicas).toBe(3);
    });

    it("scaleDeployment 缩容到 1", async () => {
      if (!k8sAvailable) return;
      const result = (await k8sExecutor(connInfo, "scaleDeployment", {
        namespace: TEST_NS,
        name: DEPLOY_NAME,
        replicas: 1,
      })) as { scaled: boolean; replicas: number };

      expect(result.scaled).toBe(true);
      expect(result.replicas).toBe(1);
    });

    it("restartDeployment 重启", async () => {
      if (!k8sAvailable) return;
      const result = (await k8sExecutor(connInfo, "restartDeployment", {
        namespace: TEST_NS,
        name: DEPLOY_NAME,
      })) as { restarted: boolean; name: string };

      expect(result.restarted).toBe(true);
      expect(result.name).toBe(DEPLOY_NAME);
    });
  });

  // ── 危险操作 ────────────────────────────────────────

  describe("危险操作", () => {
    it("deletePod 删除一个 pod (K8s 会自动重建)", async () => {
      if (!k8sAvailable) return;

      // 用 kubectl 直接 scale，避免 resourceVersion 冲突
      execSync(
        `kubectl -n ${TEST_NS} scale deployment/${DEPLOY_NAME} --replicas=2`,
        { encoding: "utf-8", timeout: 15_000 },
      );
      execSync(
        `kubectl -n ${TEST_NS} rollout status deployment/${DEPLOY_NAME} --timeout=30s`,
        { encoding: "utf-8", timeout: 40_000 },
      );

      const pods = (await k8sExecutor(connInfo, "listPods", {
        namespace: TEST_NS,
      })) as Array<{ name: string; status: string }>;
      const runningPod = pods.find((p) => p.status === "Running");
      if (!runningPod) return;

      const result = (await k8sExecutor(connInfo, "deletePod", {
        namespace: TEST_NS,
        name: runningPod.name,
      })) as { deleted: boolean; pod: string };

      expect(result.deleted).toBe(true);
      expect(result.pod).toBe(runningPod.name);
    }, 60_000);
  });

  // ── executeService 注册流程 ──────────────────────────

  describe("executeService 端到端", () => {
    it("注册 K8s service + listPods", async () => {
      if (!k8sAvailable) return;

      const serviceId = await insertServiceRecord({
        name: "test-k8s-exec",
        serviceType: "kubernetes",
        host: "localhost",
        port: 6443,
        config: { kubeconfig: proxyKubeconfig },
      });

      const pods = (await executeService(serviceId, "listPods", {
        namespace: TEST_NS,
      })) as Array<{ name: string }>;

      expect(pods.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 错误处理 ──────────────────────────────────────────

  describe("错误处理", () => {
    it("不存在的 pod 报错", async () => {
      if (!k8sAvailable) return;
      await expect(
        k8sExecutor(connInfo, "describePod", {
          namespace: TEST_NS,
          name: "nonexistent-pod-xyz",
        }),
      ).rejects.toThrow();
    });

    it("不支持的 operation 报错", async () => {
      if (!k8sAvailable) return;
      await expect(k8sExecutor(connInfo, "unknownOp", {})).rejects.toThrow(
        'unsupported operation "unknownOp"',
      );
    });
  });
});
