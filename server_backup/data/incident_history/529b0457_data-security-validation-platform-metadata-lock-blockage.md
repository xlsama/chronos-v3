# 事件排查报告

## 事件概要
- **标题**: 数据安全校验平台接口返回空数据（元数据锁阻塞导致服务假死）
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
- **受影响服务**: 数据安全校验平台 (`yum-data-security`)
- **症状**: 前端页面及调用方访问 `/api/sys/check/data` 等接口时，返回“暂无数据”或 HTTP 500 错误。
- **影响范围**: 依赖该平台进行数据合规校验的内部业务系统无法获取校验结果，可能导致业务数据流转阻塞。

## 排查过程
1. **信息收集与假设建立**：
   - 确认项目为“数据安全校验平台”，核心功能为异步批量校验敏感数据。
   - 初步假设 H1：上游未提交数据或任务未完成；H2：查询逻辑/数据库异常；H3：配置过滤过严。
   - 优先验证 H1，检查数据库审计日志和 Redis 队列。

2. **数据层排查**：
   - 检查 MySQL 数据库 `yum_data` 中的表结构，确认存在 `sys_application`, `sys_audit_log`, `check_status` 等关键表。
   - 分析 `sys_audit_log` 发现：`/api/check/data` 接口近期有 473 次 POST 请求，但均返回 **500 错误**；`/api/sys/check/data` 仅有 1 次 GET 记录。
   - 结论：业务方确实提交了数据，但服务端处理失败，非“无数据”问题。

3. **应用层日志分析**：
   - 查看容器 `yum-data-security` 日志，发现大量报错：`HikariPool-1 - Connection is not available, request timed out after 30001ms`。
   - 判定：应用数据库连接池耗尽，导致服务无法响应新请求。

4. **数据库深层诊断**：
   - 检查 `information_schema.processlist`，发现多个会话处于 `Waiting for table metadata lock` 状态，且等待时间长达 200+ 秒。
   - 锁定目标表：`check_status` 表被持有元数据锁（In_use=1）。
   - 定位阻塞源：发现一个 ID 为 `1251778` 的会话处于 `Sleep` 状态已达 264 秒，该会话持有 `check_status` 表的元数据锁但未释放。
   - 进一步排查 `innodb_trx` 和 `metadata_locks`，确认该会话可能因未提交事务或异常断开导致锁未释放，进而阻塞了所有后续的 DDL/DML 操作。

5. **执行修复**：
   - 执行 `KILL 1251778;` 终止阻塞会话，释放元数据锁。
   - 执行 `docker restart yum-data-security` 重启应用容器，重建 Hikari 连接池。

6. **验证恢复**：
   - 健康检查接口返回 HTTP 200。
   - 数据库查询正常，无锁等待现象。
   - 业务接口返回预期响应（需 Token 认证，说明服务逻辑已恢复）。

## 根因分析
根本原因为 **MySQL 元数据锁（Metadata Lock）阻塞**。
具体链路如下：
1. 一个数据库会话（ID: 1251778）在操作 `check_status` 表后，持有元数据锁进入 `Sleep` 状态，但未及时提交事务或关闭连接。
2. 该锁导致后续所有对该表的读写操作（包括业务提交的 INSERT 和查询 SELECT）全部阻塞在 `Waiting for table metadata lock` 状态。
3. 应用层的 Hikari 连接池中的所有连接均被占用且超时，无法获取新连接。
4. 服务最终抛出 `CannotGetJdbcConnectionException`，接口返回 500 错误，前端展示为空数据。

## 修复措施
1. **紧急止损**：
   - 执行 SQL 命令 `KILL 1251778;` 强制终止持有元数据锁的阻塞会话。
   - 重启应用容器 `yum-data-security`，重置耗尽的数据库连接池。

2. **验证结果**：
   - 服务健康检查通过（HTTP 200）。
   - 数据库进程列表恢复正常，无长时等待的锁会话。
   - 接口调用恢复正常，能够正确响应业务请求。

## 注意事项
- **长期优化建议**：
  - **事务管理**：排查产生会话 1251778 的客户端代码，确保所有 DDL/DML 操作后正确执行 `COMMIT` 或 `ROLLBACK`，避免长事务或未提交事务。
  - **监控告警**：增加对 `information_schema.processlist` 中 `Waiting for table metadata lock` 状态的监控，设置阈值告警。
  - **连接池配置**：优化 HikariCP 配置，启用 `leakDetectionThreshold` 检测连接泄漏，合理设置 `maxLifetime`。
  - **架构优化**：对于涉及表结构变更的操作，建议在低峰期执行或采用在线 DDL 工具（如 pt-online-schema-change），减少对业务的阻塞影响。