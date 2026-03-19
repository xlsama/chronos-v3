# 事件排查报告

## 事件概要
- 标题: KFC系统数据库表结构与数据量查询  
- 严重程度: P3  
- 处理状态: 已解决  

## 问题描述
用户请求查询KFC系统的数据库表结构及各表数据量。此为系统元数据查询需求，不属于故障事件范畴。初始排查中发现数据库连接失败，需定位正确的连接配置以获取目标信息。

## 排查过程
1. **环境初步检查**  
   - 调用 `list_servers` 确认服务器状态为在线（localhost）  
   - 检查宿主机端口：`psql -h localhost -p 5433` 连接被拒绝  
   - 验证容器环境：发现 `.dockerenv` 文件标记为Docker容器  

2. **配置文件分析**  
   - 读取 `/app/entrypoint.sh` 发现默认数据库主机名为 `postgres`  
   - 通过 `drizzle.config.ts` 确认连接URL：`postgres://kfc:kfc123@localhost:5433/kfc_monitor`  

3. **连接验证**  
   - 首次尝试使用 `localhost:5433` 失败（Connection refused）  
   - 改用 `host=postgres` 执行 `psql -h postgres -U kfc -d kfc_monitor` 成功登录  

4. **数据提取与验证**  
   - 执行 `\dt` 列出5张基础表  
   - 使用 `pg_stat_user_tables` 和 `COUNT(*)` 双重验证各表行数  
   - 通过schema定义确认字段结构与关系逻辑一致性  

## 根因分析
- 初始连接失败源于未识别容器内服务拓扑，默认配置将数据库主机组件映射为 `postgres` 而非 `localhost`  
- 数据库凭证硬编码在启动脚本中（PGPASSWORD=kfc123），环境变量未提供动态配置  
- 应用层通过drizzle ORM管理Schema，但未暴露实时数据量统计接口  

## 修复措施
- **执行操作**  
  ```bash
  # 使用容器网络内部主机名连接
  PGPASSWORD=kfc123 psql -h postgres -U kfc -d kfc_monitor
  
  # 统计所有表行数据（双重验证）
  SELECT relname, n_live_tup FROM pg_stat_user_tables;
  ```
- **验证结果**  
  | 表名                | 数据行数 |  
  |---------------------|----------|  
  | stores              | 15       |  
  | equipment           | 60       |  
  | alerts              | 29       |  
  | inspection_records  | 20       |  
  | daily_sales         | 45       |  
  - 总计169行数据，两次查询结果完全一致  
  - Schema定义与物理表结构匹配