# 数据安全校验平台（yum-data-security）项目介绍

## 一、项目简介

**数据安全校验平台**是一个面向企业内部多应用的数据合规校验系统。各业务应用通过注册并获取 AccessKey 后，可将待校验数据提交到平台，平台基于预配置的正则表达式规则（如身份证号、手机号等敏感信息检测），对数据进行异步批量校验，并返回校验结果（合规/不合规及违规明细）。

平台同时提供管理后台（Web 端），供管理员管理用户、应用、校验规则、查看校验记录及配置系统参数。

### 核心校验流程

```
1. 管理员注册应用，生成 AccessKey
2. 外部应用通过 API 提交待校验数据（JSON 列表 + client-key Header）
3. 平台将原始数据存入 MongoDB，在 MySQL 中创建校验任务记录（状态：等待校验）
4. 异步线程池拉取待校验任务，遍历数据中的每个字段值
5. 对每个字段值依次应用所有已启用的正则规则进行匹配
6. 若匹配到敏感信息 → 标记为"不合规"，记录违规字段名和字段值
7. 若所有字段均通过 → 标记为"合规"
8. 校验完成后，向 sys_webhook 表中已启用的外部 webhook 地址发送 HTTP POST 通知
9. 外部应用通过 jobId 查询校验结果
```

**校验状态码：**

| 状态码 | 含义 | 说明 |
|--------|------|------|
| 0 | 合规 | 所有字段均未匹配到敏感信息 |
| 1 | 不合规 | 至少有一个字段匹配到敏感信息规则 |
| 2 | 等待校验 | 数据已提交，尚未开始校验 |
| 3 | 正在校验 | 异步线程正在执行规则匹配 |

---

## 二、前端页面及功能

前端项目位于 `yum-data-security-web`，共 6 个页面：

### 1. 登录页

- **表单字段**：用户名、密码
- 登录成功后将 JWT Token 和用户名存储到 localStorage，自动跳转至校验记录页

### 2. 校验记录页（/dataCheck/checkRecord）

校验记录是平台的核心查看页面，展示所有外部应用提交的数据校验任务及其结果。

**表格视图 — 列定义：**

| 列名 | 说明 |
|------|------|
| 任务编码 | 校验任务唯一标识（jobId） |
| 应用名称 | 提交数据的应用名称（关联 sys_application） |
| 提交用户 | 提交校验请求的用户名 |
| 校验状态 | 合规（绿色圆点）/ 不合规（红色圆点） |
| 开始时间 | 校验任务创建时间 |
| 结束时间 | 校验完成时间 |
| 失败明细 | 不合规时显示违规字段名和字段值（如：`不合规字段值 column=phone,value=13800138000`） |

**筛选条件：**
- 日期范围选择器（开始日期 ~ 结束日期，精确到秒）
- 应用多选下拉框
- 校验状态多选（合规 / 不合规）
- 关键字搜索
- 支持按列排序（升序/降序）

**图表视图：**
- 堆叠柱状图，X 轴为应用名称，Y 轴为校验次数
- 两个系列：合规（绿色 #64BF30）和不合规（红色 #E86452）
- 直观展示各应用的合规/不合规数据比例

**导出功能：**
- 导出为 Excel 文件（校验记录.xlsx），包含筛选后的全部记录

### 3. 校验规则页（/dataCheck/checkRules）

管理平台使用的正则表达式校验规则，如身份证号、手机号等敏感信息检测规则。

**表格列：**

| 列名 | 说明 |
|------|------|
| 规则名称 | 规则的业务名称（如"身份证号校验"） |
| 规则内容 | 正则表达式（如 `(^\d{15}$)|(^\d{17}([0-9]|X)$)`） |
| 规则描述 | 规则用途的文字说明 |
| 创建时间 | 规则创建时间 |
| 更新时间 | 规则最后修改时间 |
| 启用 | 开关控件，控制规则是否参与校验 |
| 操作 | 规则测试、编辑、删除 |

**新增/编辑表单（抽屉弹窗）：**
- 规则名称（必填）
- 规则描述（必填）
- 规则内容（必填，填写正则表达式）

**规则测试功能：**
- 输入任意文本作为验证内容
- 点击"验证"按钮，平台用该规则的正则对内容进行匹配
- 显示结果："验证通过"（未匹配到敏感信息）或"验证未通过"（匹配到敏感信息）

### 4. 用户管理页（/dataCheck/userManage）

管理可登录管理后台的系统用户。

**表格列：** 用户名称、创建时间、更新时间、启用开关、操作（编辑、删除）

**新增/编辑表单（弹窗）：**
- 用户名（必填）
- 密码（必填）

### 5. 应用管理页（/dataCheck/appManage）

管理接入平台的外部业务应用，每个应用代表一个需要进行数据安全校验的业务系统。

**表格列：** 应用名称（可点击进入详情页）、应用编码、创建时间、更新时间、启用开关、操作（编辑、删除）

**新增/编辑表单（弹窗）：**
- 应用名称（必填）

### 5.1 应用详情页 — AccessKey 管理（/dataCheck/appDetails）

管理指定应用的 API 访问密钥，外部应用调用校验接口时需在 Header 中携带 AccessKey 进行身份认证。

**表格列：** AccessKey（密钥 ID）、状态开关、生成时间、操作（删除）

**生成 AccessKey 流程：**
1. 点击"生成 Access Key"按钮
2. 系统生成 UUID 格式的 AccessKey
3. 弹窗展示 AccessKey Secret，并提示：**"请及时保存或发送 AccessKey 信息至对应用户，弹窗关闭后将无法再次获取该信息，但您可随时创建新的 AccessKey"**
4. 支持一键复制 AccessKey Secret 到剪贴板

### 6. 系统配置页（/dataCheck/systemSet）

配置校验任务执行的线程池参数，控制异步校验的并发能力。

**配置项：**
- 线程池最小核心数（必填，最小值 0）
- 线程池最大核心数（必填，最小值 0，提示：最大核心数应大于最小核心数）
- 线程队列长度（必填，最小值 0）

---

## 三、后端接口清单

后端项目位于 `yum-data-security`，共 11 个 Controller，接口如下：

### 1. SysUserController（/api/sys/user）— 用户管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /login | 用户登录，返回 JWT Token |
| GET | /queryUserList | 分页查询用户列表 |
| GET | /queryDetails | 根据 ID 或用户名查询用户详情 |
| POST | /save | 新增或更新用户 |
| DELETE | /{id} | 删除用户 |
| GET | /updateEnable | 启用/禁用用户 |

### 2. SysApplicationController（/api/sys/app）— 应用管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /queryAppList | 分页查询应用列表 |
| GET | /queryDetails | 查询应用详情 |
| POST | /save | 新增或更新应用 |
| DELETE | /{id} | 删除应用 |
| GET | /updateEnable | 启用/禁用应用 |

### 3. SysAccessKeyController（/api/sys/AccessKey）— AccessKey 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /queryAccessKeyList | 查询指定应用的 AccessKey 列表 |
| GET | /createAccessKey | 为应用生成新的 AccessKey |
| DELETE | /{id} | 删除 AccessKey |
| GET | /updateEnable | 启用/禁用 AccessKey |

### 4. SysRegularController（/api/sys/rule）— 校验规则管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /queryRulesList | 分页查询校验规则列表 |
| GET | /queryDetails | 查询规则详情 |
| POST | /save | 新增或更新校验规则 |
| DELETE | /{id} | 删除规则 |
| GET | /updateEnable | 启用/禁用规则 |
| GET | /checkRules | 测试正则规则是否匹配指定内容 |

### 5. SysConfigController（/api/sys/config）— 系统配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /query | 查询系统配置（线程池参数） |
| POST | /saveOrUpdate | 新增或更新系统配置 |

### 6. CheckDataController（/api/check/data）— 数据校验提交

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | / | 外部应用提交待校验数据（需在 Header 中传入 `client-key`），返回 jobId |

### 7. CheckStatusController（/api/check/status）— 校验状态查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /{jobId} | 外部应用根据 jobId 查询校验结果（需 `client-key` Header） |

### 8. SysCheckStatusController（/api/sys/check/status）— 校验记录管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /queryCheckList | 分页查询校验记录列表 |
| POST | /queryCheckTreeFigure | 获取校验数据的树状/图表结构 |
| GET | /queryAppFilterData | 获取应用筛选下拉数据 |
| POST | /queryCheckList/export | 导出校验记录为 Excel |
| GET | /clear/col | 按日期清理过期的 MongoDB 集合 |

### 9. SysCheckDataController（/api/sys/check/data）— 校验数据（内部）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /rule | 测试接口，获取校验规则 |

### 10. CheckServiceController（/api/check/service）— 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | / | 服务健康检查端点 |

### 11. MaintenanceController（/api/sys/maintenance）— 数据维护

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /optimize | 执行 check_status 表优化维护（参数：duration 秒数，默认 30），对表加写锁后进行数据分析和整理 |

---

## 四、页面与接口映射

| 页面 | 调用接口 |
|------|----------|
| **登录页** | `GET /api/sys/user/login` |
| **校验记录页** | `POST /api/sys/check/status/queryCheckList`<br>`GET /api/sys/check/status/queryAppFilterData`<br>`POST /api/sys/check/status/queryCheckTreeFigure`<br>`POST /api/sys/check/status/queryCheckList/export` |
| **校验规则页** | `POST /api/sys/rule/queryRulesList`<br>`GET /api/sys/rule/queryDetails`<br>`POST /api/sys/rule/save`<br>`GET /api/sys/rule/updateEnable`<br>`GET /api/sys/rule/checkRules`<br>`DELETE /api/sys/rule/{id}` |
| **用户管理页** | `GET /api/sys/user/queryUserList`<br>`GET /api/sys/user/queryDetails`<br>`POST /api/sys/user/save`<br>`GET /api/sys/user/updateEnable`<br>`DELETE /api/sys/user/{id}` |
| **应用管理页** | `POST /api/sys/app/queryAppList`<br>`GET /api/sys/app/queryDetails`<br>`POST /api/sys/app/save`<br>`GET /api/sys/app/updateEnable`<br>`DELETE /api/sys/app/{id}` |
| **应用详情页** | `GET /api/sys/AccessKey/queryAccessKeyList`<br>`GET /api/sys/AccessKey/createAccessKey`<br>`GET /api/sys/AccessKey/updateEnable`<br>`DELETE /api/sys/AccessKey/{id}` |
| **系统配置页** | `GET /api/sys/config/query`<br>`POST /api/sys/config/saveOrUpdate` |

**外部应用接入接口（非管理后台页面）：**

| 调用方 | 接口 | 说明 |
|--------|------|------|
| 外部业务应用 | `POST /api/check/data` | 提交校验数据 |
| 外部业务应用 | `GET /api/check/status/{jobId}` | 查询校验结果 |
| 外部业务应用 | `GET /api/check/service` | 健康检查 |

### 外部应用接入说明

**提交校验数据：** `POST /api/check/data`

请求 Header：
```
client-key: <AccessKeyId>
```

请求 Body：
```json
{
  "checkData": [
    { "field1": "value1", "field2": "value2" },
    { "field1": "value3", "field2": "value4" }
  ],
  "userInfo": {
    "userId": "用户ID",
    "userName": "用户名"
  }
}
```

响应：
```json
{
  "code": 0,
  "msg": "success",
  "data": { "jobId": "任务ID" }
}
```

**查询校验结果：** `GET /api/check/status/{jobId}`

请求 Header：
```
client-key: <AccessKeyId>
```

响应：
```json
{
  "code": 0,
  "msg": "success",
  "data": { "status": 0 }
}
```

> status 取值：0=合规、1=不合规、2=等待校验、3=正在校验

---

## 五、技术栈

### 前端

- **框架**：Vue 2.6 + Vue Router + Vuex
- **UI 组件库**：Ant Design Vue 1.7
- **HTTP 客户端**：Axios
- **图表**：ECharts 5
- **构建工具**：Vue CLI
- **样式**：Sass / Less

### 后端

- **框架**：Spring Boot 2.6.4
- **ORM**：MyBatis Plus 3.4
- **数据库**：MySQL 8.0 + MongoDB
- **缓存**：Redis（已配置但当前未启用）
- **认证**：JWT（Auth0 java-jwt）+ Apache Shiro
- **加密**：BouncyCastle（RSA/AES）
- **工具库**：Hutool 5.7、Apache Commons
- **Excel 导出**：Apache POI 4.1
- **构建**：Maven、Java 17
- **部署**：Docker

---

## 六、DEV 环境数据库连接信息

> 以下为 DEV 环境配置（对应 Dockerfile 中 `-Pdev` 构建 profile，服务端口 8082）

### 服务器 SSH

| 配置项 | 值 |
|--------|-----|
| OS | CentOS |
| Host | 10.200.100.85 |
| Username | admin |
| Password | OJ#6QB0&6w4Q |

### MySQL

| 配置项 | 值 |
|--------|-----|
| Host | 10.200.100.8 |
| Port | 3306 |
| Database | yum_data |
| Username | root |
| Password | Password01! |
| JDBC URL | `jdbc:mysql://10.200.100.8:3306/yum_data?useUnicode=true&characterEncoding=UTF-8&autoReconnect=true&useSSL=false&zeroDateTimeBehavior=convertToNull&serverTimezone=Asia/Shanghai` |

### MongoDB

| 配置项 | 值 |
|--------|-----|
| Host | 10.200.100.85 |
| Port | 27017 |
| Database | yum_check |
| Username | root |
| Password | Password01! |
| Auth Source | admin |
| URI | `mongodb://root:Password01!@10.200.100.85:27017/yum_check?authSource=admin` |

### Redis（当前未启用）

| 配置项 | 值 |
|--------|-----|
| Host | 10.200.100.9 |
| Port | 6379 |
| Timeout | 5000ms |

> **注意：** Redis 在配置文件中保留了连接信息，但当前项目中**实际未使用**。pom.xml 中的 Redisson 依赖已被注释，`RedisRepositoryHelper` 工具类整体被注释。原计划用于 JWT Token 缓存（登录后将加密 Token 存入 Redis，校验时比对是否过期），但该功能未启用，当前认证直接通过 JWT 本身的过期时间控制。

---

## 七、数据模型

### MySQL 表

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| sys_user | 系统用户 | id, userName, userPassword, isEnable |
| sys_application | 接入应用 | id, applicationId, applicationCode, applicationName, accessToken, isEnable |
| sys_access_key | 应用访问密钥 | id, AccessKeyId, applicationId, isEnable |
| sys_regular | 校验规则（正则） | id, regularName, regularContent, regularDescribe, isEnable（支持逻辑删除） |
| check_status | 校验任务状态 | id, AccessKeyId, chectDataId, status(0成功/1失败/2待处理/3处理中), exceptionDetails |
| sys_config | 系统配置（线程池） | id, corePoolSize, maxPoolSize, queueCapacity, threadNamePrefix, isEnable |
| sys_audit_log | 审计日志（自动建表） | id, request_method, request_uri, query_string, client_ip, response_status, duration_ms, create_time |
| sys_webhook | Webhook 通知配置 | id, webhook_name, webhook_url, isEnable（0启用/1禁用）, create_time, update_time |

### MongoDB

- **数据库**：yum_check
- **用途**：存储外部应用提交的原始校验数据，每次校验任务生成一个文档，通过 `chectDataId` 与 MySQL 的 `check_status` 表关联

---

## 八、定时任务

| 任务 | Cron 表达式 | 说明 |
|------|-------------|------|
| DropMongoColTask | `0 0 0 * * ?`（每日零点） | 清理过期的 MongoDB 集合，释放存储空间 |

---

## 九、认证机制

- **管理后台**：JWT Token 认证，登录后获取 Token，后续请求通过 Header 携带 Token
  - Token 有效期：7200 秒（2 小时）
  - 拦截路径：`/api/**`
  - 免认证路径：`/**/login`、`/api/check/service`、`/api/check/status/**`、`/api/check/data`、`/actuator/**`、`/api/sys/maintenance/**`
- **外部应用 API**：通过 HTTP Header `client-key` 传递 AccessKeyId 进行身份验证
- **审计日志**：`AuditLogFilter`（Servlet Filter）自动记录所有 HTTP 请求的方法、URI、客户端 IP、响应状态和耗时到 `sys_audit_log` 表
- **Webhook 通知**：`WebhookNotifyHelper` 在数据校验完成后，向 `sys_webhook` 表中已启用的外部地址发送 HTTP POST 通知（包含 checkStatusId、status、details）
