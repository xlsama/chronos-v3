# Kubernetes 集群运维手册

本文档记录了生产环境 K8s 集群的日常运维要点。

## 节点管理

集群共有 3 个 Master 节点和 12 个 Worker 节点，使用 Calico 作为 CNI 插件。

节点标签规范：
- `env=production` 生产节点
- `env=staging` 预发布节点

## 常用排查命令

查看 Pod 状态：`kubectl get pods -A --field-selector status.phase!=Running`

查看节点资源：`kubectl top nodes`

## 告警处理

当 CPU 使用率超过 80% 时，Prometheus 会触发告警并通过飞书通知 oncall 人员。
