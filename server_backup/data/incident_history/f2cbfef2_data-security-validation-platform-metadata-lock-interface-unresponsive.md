# 事件排查报告

## 事件概要
- **标题**: 数据安全校验平台接口无响应（MySQL 元数据锁导致连接池耗尽）
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
- **受影响服务**: 数据安全校验平台 (`yum-data-security` 容器)
- **症状**: 外部业务应用调用 `POST /api/check/data` 等接口时出现超时，请求无响应。健康检查接口 `GET /health` 也出现超时。
- **影响范围**: 所有接入该平台的业务应用无法进行数据合规校验，可能导致业务数据发布流程受阻。

## 排查过程
1. **环境确认**: 
   - 定位到目标服务器 `DEV Server` (10.200.100.85)。
   - 确认容器 `yum-data-security` 处于运行状态 (`Up 4 minutes`)，监听端口 8082。

2. **症状复现与初步分析**:
   - 执行 `curl localhost:8082/health` 验证，发现命令执行超时（10秒），确认服务进程虽在但接口不可用。
   - 检查容器日志，发现大量数据库异常：`HikariPool-1 - Connection is not available, request timed out after 30000ms`。表明应用无法从连接池获取数据库连接。

3. **数据库侧深入排查**:
   - 登录 MySQL 数据库 (`c74680ff-467c-4a44-ab70-0f1e586a624d`) 执行 `SHOW PROCESSLIST;`。
   - **关键发现**: 多个来自应用服务器 IP (`10.200.100.85`) 的连接处于 `Waiting for table metadata lock` 状态，且等待时间长达 200-258 秒。涉及的 SQL 包括对 `check_status` 表的 `INSERT` 和 `SELECT` 操作。
   - 检查 InnoDB 事务表 (`INNODB_TRX`) 为空，排除长事务持有行锁的可能。
   - 进一步筛选 `yum_data` 库下的 `Sleep` 状态连接，发现连接 ID `1249395` (Host: `10.200.100.85:42950`) 已休眠 285 秒。

4. **根因锁定**:
   - 确定连接 ID `1249395` 为未提交事务的持有者，它持有了 `check_status` 表的元数据锁（Metadata Lock）。
   - 由于元数据锁阻塞了所有对该表的读写操作，导致应用线程全部阻塞在获取数据库连接上，最终引发连接池耗尽和服务假死。

## 根因分析
**根本原因**: MySQL 数据库中存在一个未提交的事务（会话 ID: 1249395），该会话持有了 `yum_data.check_status` 表的元数据锁长达 285 秒未释放。

**故障链条**:
1. 某个未提交的事务（可能是代码逻辑缺陷、异常中断或长时间运行的后台任务）开启了事务但未显式提交或回滚。
2. 该事务隐式或显式地持有了 `check_status` 表的元数据锁。
3. 后续业务请求尝试访问该表时，被 MySQL 内核阻塞，状态变为 `Waiting for table metadata lock`。
4. 应用层（Spring Boot + HikariCP）无法获取新的数据库连接，连接池中的连接逐渐被阻塞耗尽。
5. 当连接池耗尽后，新请求抛出 `CannotGetJdbcConnectionException` 并超时，表现为接口无响应。

## 修复措施
1. **紧急恢复**:
   - 执行命令 `KILL 1249395;` 强制终止持有元数据锁的睡眠会话。
   
2. **验证结果**:
   - **锁状态**: 再次查询 MySQL 进程列表，`Waiting for table metadata lock` 的计数归零，锁等待解除。
   - **接口响应**: 执行 `curl localhost:8082/health`，请求不再超时，返回 HTTP 404（路径不存在但服务可响应），证明服务已恢复通信能力。
   - **应用日志**: 查看最新日志，不再出现 `HikariPool` 连接超时错误，异步校验任务正常执行完成（`Completed normally`）。
   - **业务验证**: 测试业务接口 `/api/check-status/list` 返回 500 错误（参数缺失导致），非数据库连接问题，确认服务功能基本恢复。

## 注意事项与建议
- **待追溯**: 需进一步调查连接 ID `1249395` 对应的具体业务场景（如定时任务、特定接口调用），查明为何开启事务后未提交。
- **优化建议**:
  - **代码层面**: 审查涉及 `check_status` 表的代码逻辑，确保所有事务块都有明确的 `commit` 或 `rollback`，特别是在异常捕获块中。
  - **配置层面**: 考虑调整 MySQL 的 `lock_wait_timeout` 及应用端 HikariCP 的 `connectionTimeout` 策略，以缩短故障恢复时间。
  - **监控层面**: 增加对 MySQL 长时间 `Sleep` 连接及 `Waiting for table metadata lock` 状态的告警监控。