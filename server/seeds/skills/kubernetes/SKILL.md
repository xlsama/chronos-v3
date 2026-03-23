---
name: Kubernetes 排查
description: Kubernetes 集群与工作负载排查指南。当事件涉及 K8S、Pod 异常、CrashLoopBackOff、Pending、ImagePullBackOff、Evicted、OOMKilled、Deployment 滚动更新失败、Service 不通、Ingress 配置、Node NotReady、资源配额不足、HPA 扩缩容、PV/PVC 存储、ConfigMap、Secret 时使用。
metadata:
  pattern: pipeline
  domain: orchestration
  steps: "6"
---

## 执行环境说明

你是一个远程运维 Agent，不在目标服务器上运行。所有操作通过以下工具完成：

- **`service_exec(service_id, "kubectl ...")`** — 直连已注册的 Kubernetes 集群（`service_type: kubernetes`），**首选方式**
- **`ssh_bash(server_id, command)`** — 在远程目标服务器上执行 shell 命令（备选：当没有注册 K8s 服务时，通过有 kubeconfig 的管理机执行 kubectl）
- **`bash(command)`** — 仅用于本地文本处理、curl 等辅助操作

> 两种 kubectl 执行路径：
> - **直连模式**（推荐）：系统中注册了 `kubernetes` 类型的服务，通过 `service_exec` 直接执行 kubectl 命令
> - **SSH 模式**（备选）：通过 `ssh_bash` 在有 kubeconfig 的管理服务器上执行 kubectl 命令

## 第零步：定位目标（必须执行）

1. 调用 `list_services()` 获取已注册服务
2. 检查是否有 `service_type: kubernetes` 的服务：
   - **有** → 记录 `service_id`，后续所有 kubectl 命令通过 `service_exec(service_id, "kubectl ...")` 执行
   - **没有** → 调用 `list_servers()` 找一台有 kubeconfig 的管理服务器，通过 `ssh_bash(server_id, "kubectl ...")` 执行
3. 结合事件描述，确定目标 namespace 和工作负载

## 第一步：集群概览

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 集群节点 ====='; kubectl get nodes -o wide 2>/dev/null; echo ''; echo '===== 节点资源使用 ====='; kubectl top nodes 2>/dev/null || echo 'metrics-server not available'; echo ''; echo '===== 异常 Pod ====='; kubectl get pods -A --field-selector 'status.phase!=Running,status.phase!=Succeeded' 2>/dev/null; echo ''; echo '===== 最近集群事件 ====='; kubectl get events -A --sort-by='.lastTimestamp' 2>/dev/null | tail -20
```

## 第二步：Pod 排查

### Pod 状态检查

```bash
# 指定 namespace 的 Pod 列表
ssh_bash(server_id, "kubectl get pods -n <namespace> -o wide")

# Pod 详细信息（事件、条件、容器状态）
ssh_bash(server_id, "kubectl describe pod <pod-name> -n <namespace>")

# Pod 资源使用
ssh_bash(server_id, "kubectl top pod <pod-name> -n <namespace> 2>/dev/null || echo 'metrics-server not available'")
```

### Pod 日志

```bash
# 当前容器日志
ssh_bash(server_id, "kubectl logs <pod-name> -n <namespace> --tail=100")

# 上一次崩溃的日志（CrashLoopBackOff 必查）
ssh_bash(server_id, "kubectl logs <pod-name> -n <namespace> --previous --tail=100 2>/dev/null || echo 'no previous logs'")

# 多容器 Pod 指定容器
ssh_bash(server_id, "kubectl logs <pod-name> -n <namespace> -c <container-name> --tail=100")
```

### Pod 内执行命令

```bash
ssh_bash(server_id, "kubectl exec -it <pod-name> -n <namespace> -- <command>")
```

## 第三步：工作负载排查

### Deployment / StatefulSet

```bash
# Deployment 状态
ssh_bash(server_id, "kubectl get deployment -n <namespace> -o wide")

# 滚动更新状态
ssh_bash(server_id, "kubectl rollout status deployment/<name> -n <namespace>")

# 更新历史
ssh_bash(server_id, "kubectl rollout history deployment/<name> -n <namespace>")

# ReplicaSet 状态（查看新旧版本副本数）
ssh_bash(server_id, "kubectl get rs -n <namespace> -o wide")

# StatefulSet 状态
ssh_bash(server_id, "kubectl get statefulset -n <namespace> -o wide")
```

### DaemonSet / Job / CronJob

```bash
ssh_bash(server_id, "kubectl get daemonset -n <namespace> -o wide")
ssh_bash(server_id, "kubectl get jobs -n <namespace>")
ssh_bash(server_id, "kubectl get cronjobs -n <namespace>")
```

## 第四步：网络排查

### Service / Endpoint

```bash
# Service 列表
ssh_bash(server_id, "kubectl get svc -n <namespace> -o wide")

# Endpoint 检查（确认 Service 后端 Pod 是否健康）
ssh_bash(server_id, "kubectl get endpoints <service-name> -n <namespace>")

# Service 详情
ssh_bash(server_id, "kubectl describe svc <service-name> -n <namespace>")
```

### Ingress

```bash
ssh_bash(server_id, "kubectl get ingress -n <namespace>")
ssh_bash(server_id, "kubectl describe ingress <ingress-name> -n <namespace>")
```

### DNS 测试

```bash
# 从 Pod 内测试 DNS 解析
ssh_bash(server_id, "kubectl exec <pod-name> -n <namespace> -- nslookup <service-name>.<namespace>.svc.cluster.local 2>/dev/null || echo 'nslookup not available'")

# CoreDNS 状态
ssh_bash(server_id, "kubectl get pods -n kube-system -l k8s-app=kube-dns")
```

### NetworkPolicy

```bash
ssh_bash(server_id, "kubectl get networkpolicy -n <namespace>")
```

## 第五步：存储排查

```bash
# PV/PVC 状态
ssh_bash(server_id, "kubectl get pv")
ssh_bash(server_id, "kubectl get pvc -n <namespace>")

# PVC 详情（绑定状态、StorageClass）
ssh_bash(server_id, "kubectl describe pvc <pvc-name> -n <namespace>")

# StorageClass
ssh_bash(server_id, "kubectl get storageclass")
```

## 第六步：资源配额与限制

```bash
# 命名空间资源配额
ssh_bash(server_id, "kubectl get resourcequota -n <namespace>")
ssh_bash(server_id, "kubectl describe resourcequota -n <namespace>")

# LimitRange
ssh_bash(server_id, "kubectl get limitrange -n <namespace>")

# HPA 状态
ssh_bash(server_id, "kubectl get hpa -n <namespace>")
ssh_bash(server_id, "kubectl describe hpa <hpa-name> -n <namespace>")
```

## 常见问题排查

| 问题 | 排查方式 |
|------|---------|
| CrashLoopBackOff | `kubectl logs --previous` 查上次崩溃日志 + `kubectl describe pod` 查退出码 |
| Pending | `kubectl describe pod` 查 Events（调度失败原因：资源不足/节点选择器/亲和性/PVC 未绑定） |
| ImagePullBackOff | `kubectl describe pod` 查镜像名和 pull 错误 + registry 连通性 + imagePullSecrets |
| Evicted | `kubectl get pods --field-selector status.phase=Failed` + 节点磁盘/内存压力检查 |
| OOMKilled | `kubectl describe pod` 查 Last State: OOMKilled + 容器 resources.limits.memory |
| Node NotReady | `kubectl describe node <node>` 查 Conditions + 节点上 kubelet 日志 |
| Service 不通 | `kubectl get endpoints` 确认后端 Pod 是否就绪 + DNS 解析测试 |
| Ingress 不生效 | `kubectl describe ingress` + Ingress Controller 日志 |
| PVC Pending | `kubectl describe pvc` 查事件 + StorageClass provisioner 状态 |
| 滚动更新卡住 | `kubectl rollout status` + `kubectl get rs` 查新旧 ReplicaSet 副本数 |

## 注意事项

- **多 namespace**：始终指定 `-n <namespace>`，避免操作错误 namespace
- **先只读后操作**：排查阶段不执行 `kubectl delete`、`kubectl scale`、`kubectl rollout undo` 等操作
- **资源 YAML 导出**：`kubectl get <resource> -o yaml` 可查看完整配置
- **kubectl 权限**：部分集群使用 RBAC，某些操作可能无权限，注意错误提示
