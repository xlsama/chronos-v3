---
name: 磁盘与存储排查
description: 磁盘与存储空间排查指南。当事件涉及磁盘空间不足、磁盘满、No space left on device、inode 耗尽、I/O 延迟高、挂载失败、文件系统只读、LVM 扩容、RAID 降级、大文件查找、日志占满磁盘、数据库文件膨胀时使用。
metadata:
  pattern: pipeline
  domain: storage
  steps: "4"
---

## 执行环境说明

你是一个远程运维 Agent，不在目标服务器上运行。所有操作通过以下工具完成：

- **`ssh_bash(server_id, command)`** — 在**远程目标服务器**上执行 shell 命令（首选）
- **`service_exec(service_id, command)`** — 直连已注册的数据库/缓存/监控服务（无需 CLI 工具）
- **`bash(command)`** — 仅用于本地文本处理、curl 等辅助操作

> 命令中的 `localhost` / `127.0.0.1` 指的是**目标服务器自身**，不是你运行的位置。

## 第零步：定位目标（必须执行）

1. 调用 `list_servers()` 获取可用服务器列表
2. 调用 `list_services()` 获取已注册服务
3. 结合事件描述，确定目标服务器和存储问题类型

## 第一步：磁盘空间概况

通过 `ssh_bash(server_id, "...")` 执行：

```bash
echo '===== 磁盘使用 ====='; df -h -x tmpfs -x devtmpfs 2>/dev/null || df -h; echo ''; echo '===== Inode 使用 ====='; df -i -x tmpfs -x devtmpfs 2>/dev/null || df -i; echo ''; echo '===== 块设备 ====='; lsblk -f 2>/dev/null || echo 'lsblk not available'; echo ''; echo '===== 挂载信息 ====='; mount | grep -v 'tmpfs\|proc\|sys\|cgroup' | head -20
```

## 第二步：大文件/目录定位

```bash
# 一级目录空间占用排序
ssh_bash(server_id, "du -sh /* 2>/dev/null | sort -rh | head -15")

# 递进定位（找到占用最大的子目录后继续深入）
ssh_bash(server_id, "du -sh /var/* 2>/dev/null | sort -rh | head -10")
ssh_bash(server_id, "du -sh /var/log/* 2>/dev/null | sort -rh | head -10")

# 查找大文件（>100MB）
ssh_bash(server_id, "find / -xdev -type f -size +100M -exec ls -lh {} \\; 2>/dev/null | sort -k5 -rh | head -20")

# 已删除但未释放的文件（进程仍持有句柄）
ssh_bash(server_id, "lsof +L1 2>/dev/null | head -20 || echo 'lsof not available'")
```

### Docker 场景

```bash
# Docker 磁盘占用
ssh_bash(server_id, "docker system df 2>/dev/null || echo 'docker not available'")

# Docker 数据目录
ssh_bash(server_id, "du -sh /var/lib/docker/ 2>/dev/null")
ssh_bash(server_id, "du -sh /var/lib/docker/*/ 2>/dev/null | sort -rh")
```

## 第三步：I/O 性能

```bash
# 磁盘 I/O 统计
ssh_bash(server_id, "iostat -xd 1 3 2>/dev/null || echo 'iostat not available (install sysstat)'")

# I/O 按进程排序
ssh_bash(server_id, "iotop -b -n 1 --only 2>/dev/null || echo 'iotop not available'")

# 磁盘读写速率
ssh_bash(server_id, "cat /proc/diskstats | awk '{print $3,$4,$8}' | head -10")
```

## 第四步：文件系统与存储状态

### 文件系统检查

```bash
# 文件系统类型和状态
ssh_bash(server_id, "lsblk -f 2>/dev/null")

# 只读文件系统检测
ssh_bash(server_id, "mount | grep 'ro,' | grep -v 'tmpfs\|proc\|sys'")

# fstab 配置
ssh_bash(server_id, "cat /etc/fstab | grep -v '^#' | grep -v '^$'")
```

### LVM 状态

```bash
ssh_bash(server_id, "pvs 2>/dev/null || echo 'LVM not available'")
ssh_bash(server_id, "vgs 2>/dev/null")
ssh_bash(server_id, "lvs 2>/dev/null")
```

### RAID 状态

```bash
ssh_bash(server_id, "cat /proc/mdstat 2>/dev/null || echo 'no software RAID'")
ssh_bash(server_id, "mdadm --detail /dev/md* 2>/dev/null || echo 'mdadm not available'")
```

## 常见问题排查

| 问题 | 排查命令/方式 |
|------|-------------|
| No space left on device | `df -h` 确认分区 + `du -sh` 逐层定位 + `find -size +100M` 找大文件 |
| Inode 100% | `df -i` 确认 + `find / -xdev -type f \| wc -l` 统计文件数 + 定位小文件目录 |
| 已删除文件仍占用空间 | `lsof +L1` 找持有句柄的进程 + 重启进程或 truncate |
| 文件系统只读 | `mount` 查看 ro 标记 + `dmesg` 查文件系统错误 |
| I/O 延迟高 | `iostat -x` 关注 await/svctm + `iotop` 定位进程 |
| LVM 空间不足 | `vgs` 查 VFree + `lvextend` + `resize2fs/xfs_growfs` |
| RAID 降级 | `/proc/mdstat` 查阵列状态 + `mdadm --detail` |
| 日志占满磁盘 | `du -sh /var/log/*` 定位 + logrotate 配置检查 |

## 注意事项

- **先只读后操作**：排查阶段不执行 `rm`、`mkfs`、`resize2fs` 等操作，需修复时告知用户
- **find 加 -xdev**：避免跨文件系统搜索（如 /proc、/sys）
- **Docker /var/lib/docker**：不要直接删除此目录下的文件，应使用 `docker system prune`
- **LVM/RAID 操作危险**：扩容/修复前必须确认当前状态，告知用户风险
