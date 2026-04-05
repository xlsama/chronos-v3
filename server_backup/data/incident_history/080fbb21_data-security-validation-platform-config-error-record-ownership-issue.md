# 事件排查报告

## 事件概要
- **标题**: 数据安全校验平台“风控系统”记录消失及“数据平台”统计异常问题
- **严重程度**: P3
- **处理状态**: 已解决

## 问题描述
在“数据安全校验平台”的检查记录页面发现数据异常：
1. **“风控系统”** 的所有校验记录在前端页面完全消失，统计柱状图中也无法看到该应用。
2. **“数据平台”** 的合规/不合规数量显著高于历史水平（异常增高）。
3. 系统服务本身运行正常，无任何报错日志。

## 排查过程
1. **环境定位与架构分析**：
   - 确认受影响项目为“数据安全校验平台”，核心服务容器名为 `yum-data-security`。
   - 初步排查 MongoDB 发现其存储结构为按 ID 分片的集合，未包含应用归属元数据。
   - 根据用户提示，锁定 MySQL 数据库 (`yum_data`) 中的关键表进行排查。

2. **数据链路梳理**：
   - 确认应用归属解析链路为：`check_status.access_key_id` -> `sys_access_key.access_key_id` -> `sys_application.application_id`。
   - 重点检查 `yum_data` 库下的 `sys_application`（应用表）、`sys_access_key`（密钥表）和 `check_status`（检查状态表）。

3. **异常数据发现**：
   - **sys_application 表**：确认存在“风控系统”(`c4test-app-aaa-0001-fengkong`) 和“数据平台”(`c4test-app-bbb-0002-dataplat`) 两个应用配置。
   - **sys_access_key 表**：发现严重配置错误。
     - 风控系统的 Access Key (`c4test-ak-aaa-0001-fengkong`) 被错误地关联到了“数据平台”的 Application ID (`c4test-app-bbb-0002-dataplat`)。
   - **check_status 表**：统计显示有 10 条记录使用了风控系统的 Access Key，但由于上述关联错误，这些记录在统计时被归类到了“数据平台”。

## 根因分析
**根本原因**：`yum_data.sys_access_key` 表中存在配置错误。
- **具体事实**：风控系统的访问密钥 (`access_key_id`: `c4test-ak-aaa-0001-fengkong`) 在数据库中错误地指向了数据平台的应用 ID (`application_id`: `c4test-app-bbb-0002-dataplat`)。
- **影响机制**：当风控系统提交校验数据时，后端通过 `access_key_id` 查找对应的 `application_id` 进行归属统计。由于配置错误，风控系统的 10 条校验记录被错误地归集到“数据平台”名下。
- **现象解释**：
  - “风控系统”记录消失：因其记录被重定向统计到了另一个应用下。
  - “数据平台”数量激增：接收了原本属于风控系统的 10 条记录（原 6 条 + 误入 10 条 = 16 条）。
  - 柱状图异常：前端按应用名称聚合数据时，风控系统无独立数据源，导致图表中缺失。

## 修复措施
1. **执行修复操作**：
   执行 SQL 更新语句，将错误的关联关系修正回正确的应用 ID。
   ```sql
   UPDATE yum_data.sys_access_key 
   SET application_id = 'c4test-app-aaa-0001-fengkong' 
   WHERE access_key_id = 'c4test-ak-aaa-0001-fengkong';
   ```
   - **执行结果**：成功更新 1 行数据。

2. **验证修复结果**：
   - 再次查询 `sys_access_key` 表，确认映射关系已更正：
     - `c4test-ak-aaa-0001-fengkong` -> `c4test-app-aaa-0001-fengkong` (风控系统) ✅
     - `c4test-ak-bbb-0002-dataplat` -> `c4test-app-bbb-0002-dataplat` (数据平台) ✅
   - 确认各应用的 Check Status 记录数分布逻辑恢复正常（风控系统 10 条，数据平台 6 条）。

3. **后续建议**：
   - 请业务方刷新前端页面，验证“风控系统”记录是否恢复显示，且“数据平台”统计数据回归正常。
   - 建议对应用配置变更流程增加审核机制或自动化一致性校验，防止类似的人为配置错误再次发生。