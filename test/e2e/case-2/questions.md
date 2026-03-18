# Case 2: 微服务链路故障 - 测试问题集

## 问题 1: 订单接口 500 错误（自动化测试用）

**描述**: app-server 上的订单接口 /api/orders 返回 500 错误，请排查原因并修复

**排查深度**: 跨 2 台机器追踪故障链路
- app-server 日志 → 发现连接 data-server:8080 失败
- SSH 到 data-server → 发现 inventory-api 进程不存在
- 重启 inventory-api → 验证恢复

**涉及审批**: 是（重启进程）

---

## 问题 2: 库存服务响应慢

**描述**: 用户反馈下单时加载很慢，怀疑库存查询接口响应时间过长，请排查 data-server 上的库存服务性能问题

**排查深度**: 单机 DB 排查
- 检查 inventory-api 日志中的响应时间
- 检查 PostgreSQL 慢查询日志
- 检查系统资源（CPU、内存、IO）

**涉及审批**: 可能不涉及

---

## 问题 3: 数据不一致

**描述**: 有用户反馈订单中显示的商品库存数量与实际不符，请检查 order-api 和 inventory-api 之间的数据一致性

**排查深度**: 跨服务数据对比
- 查看 app-server 上 SQLite 中的订单数据
- 查看 data-server 上 PostgreSQL 中的库存数据
- 对比两边数据是否匹配

**涉及审批**: 可能不涉及
