# 事件排查报告

## 事件概要
- **标题**: 数据安全校验平台接口返回空数据（数据库元数据锁导致服务不可用）
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
- **受影响服务**: 数据安全校验平台 (`yum-data-security`)
- **症状**: 外部业务应用调用接口提交或查询数据时，接口返回空数据或无响应。服务健康检查超时，日志显示大量数据库连接池耗尽错误。
- **影响范围**: 依赖该平台的业务应用无法获取合规校验结果，数据提交后的反馈流程中断。

## 排查过程
1. **信息收集与假设构建**：
   - 确认项目为“数据安全校验平台”，涉及核心接口 `POST /api/check/data` 和 `GET /api/check/status/{jobId}`。
   - 建立三个待验证假设：H1 (上游未推送)、H2 (异步任务积压)、H3 (存储/查询异常)。优先验证 H1。

2. **环境定位与日志分析**：
   - 锁定服务器 `yum-data-security-dev-server` (10.200.100.85)，发现容器 `yum-data-security` 运行在 8082 端口。
   - 查看容器日志，发现 12:15:30 有正常的数据推送请求记录（含 `clientKey`），但随后出现大量 `HikariPool-1 - Connection is not available, request timed out after 30000ms` 错误。
   - 确认上游确实推送了数据，排除 H1 中“无推送”的可能性，故障点指向后端处理层。

3. **数据库深度排查**：
   - 执行 `SHOW PROCESSLIST`，发现多个来自应用服务器的连接处于 `Waiting for table metadata lock` 状态。
   - 执行 `SHOW OPEN TABLES`，确认表 `check_status` 被占用 (`In_use = 1`)，持有元数据锁。
   - 检查 `information_schema.INNODB_TRX`，发现存在长时间运行的事务（如 `SELECT COUNT(*)...`），虽未直接持有 DDL 锁，但结合上下文表明存在未释放的元数据锁资源。
   - 确认根本原因：数据库层面的元数据锁未释放，导致所有后续对该表的读写操作阻塞，进而耗尽应用侧的 HikariCP 连接池，服务假死。

4. **修复执行**：
   - 执行 `sudo docker restart yum-data-security` 重启应用容器，强制释放被占用的数据库连接。

5. **验证恢复**：
   - 重启后，健康检查接口返回 HTTP 200。
   - 组件状态检查显示 DB、MongoDB、DiskSpace 均为 UP。
   - 数据库进程列表恢复正常，无阻塞查询。

## 根因分析
**根本原因**：MySQL 数据库发生表级元数据锁（Metadata Lock）未释放，导致应用连接池耗尽。

**详细推导**：
1. **触发点**：上游业务应用正常推送数据至 `POST /api/check/data` 接口。
2. **故障机制**：
   - 平台在写入 `check_status` 表过程中，可能由于长事务未提交、异常代码路径或之前的 DDL 操作残留，导致该表被持有元数据锁。
   - 后续所有的 INSERT（新数据写入）和 SELECT（查询状态）请求均被 MySQL 阻塞，状态变为 `Waiting for table metadata lock`。
   - 应用端的 HikariCP 连接池不断尝试获取连接等待数据库响应，最终所有连接被占用且超时（30s），抛出 `Connection is not available` 异常。
   - 服务进程虽存活，但无法处理任何新请求，表现为接口“没有数据”。

## 修复措施
1. **紧急恢复**：
   - 执行命令 `sudo docker restart yum-data-security` 重启应用容器。
   - **效果**：强制断开了应用端所有持锁的数据库连接，释放了 MySQL 端的元数据锁，服务立即恢复可用。

2. **验证结果**：
   - 容器启动成功，日志显示 `HikariPool-1 - Start completed`。
   - 健康检查 URL (`/actuator/health`) 返回状态码 200，且所有依赖组件状态正常。
   - 数据库连接数回归正常水平，无 `Waiting for table metadata lock` 进程。

## 长期优化建议
1. **代码治理**：
   - 审查代码逻辑，确保所有数据库事务（Transaction）在 `finally` 块中正确提交或回滚，避免长事务。
   - 禁止在事务内部执行 DDL 操作（如 `ALTER TABLE`）。
   - 增加事务超时配置，防止单个慢查询占用连接过久。

2. **监控增强**：
   - 部署数据库连接池使用率监控，当使用率超过阈值（如 80%）时触发告警。
   - 增加数据库锁等待监控脚本，定期检测 `information_schema.PROCESSLIST` 中是否存在 `Waiting for table metadata lock` 状态的连接。

3. **架构优化**：
   - 评估并调整 HikariCP 配置（如 `maxLifetime`, `connectionTimeout`），提升对瞬时锁等待的容忍度。
   - 考虑引入数据库读写分离，将查询流量与写入流量隔离，减少单表锁竞争对整体服务的影响。

4. **运维规范**：
   - 建立数据库锁等待的定期巡检机制。
   - 制定针对连接池耗尽和元数据锁场景的应急预案（如快速重启服务或手动 Kill 阻塞进程）。