import * as k8s from "@kubernetes/client-node";
import type { Executor } from "../types";

function loadKubeConfig(conn: Record<string, unknown>): k8s.KubeConfig {
  const kc = new k8s.KubeConfig();
  if (conn.kubeconfig) {
    kc.loadFromString(conn.kubeconfig as string);
  } else {
    kc.loadFromDefault();
  }
  return kc;
}

export const k8sExecutor: Executor = async (conn, operation, params) => {
  const kc = loadKubeConfig(conn);
  const core = kc.makeApiClient(k8s.CoreV1Api);
  const apps = kc.makeApiClient(k8s.AppsV1Api);

  const ns = (params.namespace as string) || "default";

  const handlers: Record<string, () => Promise<unknown>> = {
    // ── Read ──
    listNamespaces: async () => {
      const res = await core.listNamespace();
      return res.items.map((n) => n.metadata?.name);
    },
    listPods: async () => {
      const res = await core.listNamespacedPod({ namespace: ns });
      return res.items.map((p) => ({
        name: p.metadata?.name,
        status: p.status?.phase,
        restarts: p.status?.containerStatuses?.[0]?.restartCount,
        ready: p.status?.containerStatuses?.every((c) => c.ready),
      }));
    },
    describePod: async () => {
      const res = await core.readNamespacedPod({
        name: params.name as string,
        namespace: ns,
      });
      return res;
    },
    getPodLogs: async () => {
      const res = await core.readNamespacedPodLog({
        name: params.name as string,
        namespace: ns,
        tailLines: (params.tail as number) ?? 100,
        container: params.container as string | undefined,
      });
      return res;
    },
    listDeployments: async () => {
      const res = await apps.listNamespacedDeployment({ namespace: ns });
      return res.items.map((d) => ({
        name: d.metadata?.name,
        replicas: d.status?.replicas,
        readyReplicas: d.status?.readyReplicas,
        availableReplicas: d.status?.availableReplicas,
      }));
    },
    describeDeployment: async () => {
      const res = await apps.readNamespacedDeployment({
        name: params.name as string,
        namespace: ns,
      });
      return res;
    },
    listServices: async () => {
      const res = await core.listNamespacedService({ namespace: ns });
      return res.items.map((s) => ({
        name: s.metadata?.name,
        type: s.spec?.type,
        clusterIP: s.spec?.clusterIP,
        ports: s.spec?.ports,
      }));
    },
    listNodes: async () => {
      const res = await core.listNode();
      return res.items.map((n) => ({
        name: n.metadata?.name,
        status: n.status?.conditions?.find((c) => c.type === "Ready")?.status,
      }));
    },

    // ── Write ──
    scaleDeployment: async () => {
      const res = await apps.patchNamespacedDeploymentScale({
        name: params.name as string,
        namespace: ns,
        body: { spec: { replicas: params.replicas as number } },
      });
      return { scaled: true, replicas: res.spec?.replicas };
    },
    restartDeployment: async () => {
      const now = new Date().toISOString();
      const res = await apps.patchNamespacedDeployment({
        name: params.name as string,
        namespace: ns,
        body: {
          spec: {
            template: {
              metadata: { annotations: { "kubectl.kubernetes.io/restartedAt": now } },
            },
          },
        },
      });
      return { restarted: true, name: res.metadata?.name };
    },

    // ── Dangerous ──
    deletePod: async () => {
      await core.deleteNamespacedPod({
        name: params.name as string,
        namespace: ns,
      });
      return { deleted: true, pod: params.name };
    },
  };

  const handler = handlers[operation];
  if (!handler) {
    throw new Error(
      `Kubernetes: unsupported operation "${operation}". Available: ${Object.keys(handlers).join(", ")}`,
    );
  }

  return handler();
};
