# SQLPilot 程序执行过程技术走读

> 本文不按“RAG、模型、数据库”等技术主题拆分，而是严格按照一次请求在程序中的执行顺序说明：执行到哪里、输入什么、做什么、输出什么、失败时如何处理。

## 1. 示例需求

以下流程统一使用这个案例：

```text
第一轮：查一下今年各医院的住院费用。
第二轮：医疗总费用。
第三轮：按结算日期统计。
确认后执行查询。
```

最终业务要求：以结算日期为时间口径，统计今年截至当前日期各医院住院医疗总费用，每家医院汇总一行。

## 1A. 在线查询之前：离线环境准备阶段

下面这些步骤不是每次查询都执行。它们在系统首次部署、接入新数据源、数据库结构变化或人工业务语义调整后执行，为在线Agent准备可检索、可校验的工具环境。

### 离线步骤P01：启动基础组件并读取配置

Docker Compose启动SQLPilot服务；系统库保存账号、数据源、会话、计划和治理配置，业务PostgreSQL保存客户业务数据，知识PostgreSQL通过`pgvector`和`pg_trgm`保存Schema知识。

应用启动时`app/main.py`创建数据库连接、Repository、规划器、Schema Retriever、知识库、语义层、记忆服务和查询引擎，并把它们注册到`app.state`。关键配置来自`.env`、`.env.database.local`和`.env.knowledge.local`，包括模型、Embedding、系统库、业务库、知识库和认证密钥。

失败处理：配置不完整时不会伪装成模型可用；健康接口返回`configuration_required`。生产环境不得把明文密钥提交到代码仓库。

### 离线步骤P02：初始化系统表和管理员

`Database.initialize()`使用SQLAlchemy创建当前缺失的系统表。`AuthService.bootstrap_admin()`仅在用户表为空时创建初始管理员，并把原型阶段`local-user`的会话、偏好和反馈迁移给该管理员。

管理员随后在用户管理页创建分析人员账号。用户登录只决定“谁在操作”，不等于已经获得患者级数据权限。

### 离线步骤P03：管理员录入数据源

页面：`/admin/data-sources`  
接口：`POST /api/v1/data-sources`

管理员填写数据库类型、主机、端口、库名、账号、密码和允许扫描的Schema。当前正式实现只接受PostgreSQL。程序先使用`protect_secret()`加密数据库密码，再写入`data_sources`；API响应、RAG文档和模型Prompt都不包含连接密码。

业务数据库账号应只具备目标Schema的`SELECT`权限。应用层只读校验不能替代数据库最小权限。

### 离线步骤P04：连接测试

接口：`POST /api/v1/data-sources/{source_id}/test`

`DataSourceService.test()`临时解密连接密码，通过`asyncpg`建立连接，执行`SELECT version()`和`SHOW default_transaction_read_only`，然后在`finally`中关闭连接。

失败只返回去敏后的错误类型，不把密码或完整数据库错误暴露到前端，也不交给大模型猜测。

### 离线步骤P05：配置允许访问的Schema和基础业务规则

数据源记录中的`schemas_json`限定后续扫描与查询白名单。管理员还可以配置“仅有效结算”“排除撤销”等数据源级默认规则。规则只在业务字段和码值已经核验时启用，不能仅凭字段名称自动认定。

### 离线步骤P06：提交Schema后台同步任务

接口：`POST /api/v1/data-sources/{source_id}/sync`

`queue_sync()`先检查同一数据源是否已有`queued/running`任务，存在时返回原`job_id`，避免重复构建。否则创建`SchemaSyncJobRecord`，再由FastAPI `BackgroundTasks`调用`sync()`。

状态顺序：

```text
queued → connecting → catalog_scanned → embedding → activating → ready
```

前端通过`GET /api/v1/data-sources/{source_id}/sync/latest`轮询进度。当前后台任务适合单机；生产多实例需要换成持久任务队列和分布式锁。

### 离线步骤P07：扫描数据库目录

`DataSourceService.sync()`连接业务库后查询`information_schema.columns`、`pg_class`、`pg_namespace`、`pg_attribute`和`pg_constraint`，获取：

- Schema、表、视图、字段顺序和数据库类型；
- 表注释、字段注释、可空性；
- 外键两端的表和字段；
- 适合作为业务维度的低基数字段值。

系统只对名称或注释符合类型、状态、类别、等级等特征的字段采样，最多扫描限定数量的候选字段，每列只保留少量不同值。姓名、电话、地址、证件号等疑似敏感字段以及高基数字段不会写入字典样本。

### 离线步骤P08：合并人工Schema治理信息

页面：`/admin/schema`

数据库注释往往不足以表达医保业务语义。系统读取`schema_catalog_overrides`，把管理员填写的中文名称、业务描述、别名和启停状态合并到原始目录。被停用的表或字段不会进入新知识版本。

人工信息不会直接修改客户业务库，只作为SQLPilot治理层覆盖信息保存。修改后需要重新同步，才能进入新的向量知识版本。

### 离线步骤P09：构建三级Schema知识文档

同步程序生成三类文档：

1. **表文档**：Schema、表名、表注释、人工业务说明和启用字段摘要，用于主题表召回；
2. **字段文档**：每个字段独立生成，拼接表名、表注释、字段名、类型、字段注释、中文名、别名和安全的字典值，用于精确字段绑定；
3. **关系文档**：记录外键两端，用于JOIN候选和桥接路径。

字段文档示例：

```text
Schema nhsa；表名 setl_d；表注释 医保结算主表；
字段名 medfee_sumamt；字段类型 numeric；
字段注释与业务别名 医疗总费用、费用总额
```

### 离线步骤P10：计算Schema指纹和版本号

程序把数据库目录和人工覆盖元数据规范化为排序后的JSON，再计算SHA-256指纹。版本号由时间戳和指纹前缀组成。

指纹用于回答“这次查询依据的是哪版结构”，并检测字段删除、注释修改或人工语义变化。Schema改变时，依赖旧指纹的已认证查询路径会被标记失效，不能无条件复用。

### 离线步骤P11：批量调用Embedding模型

`PgVectorKnowledgeStore.embed()`按配置批次调用百炼`text-embedding-v4`，当前维度为1,024，每批最多10篇文档。返回结果按接口中的`index`排序，保证向量与输入文档严格一一对应。

正式知识库连接或Embedding调用失败时，同步任务进入`failed`并保留上一个可用版本，不会把半成品知识用于在线查询。本地哈希向量只作为未配置正式知识库时的开发回退，不代表生产Embedding效果。

### 离线步骤P12：写入pgvector并原子激活

`replace_version()`在一个数据库事务中：

1. 创建状态为`building`的新`schema_versions`记录；
2. 写入表、字段和关系文档及其向量；
3. 将同一数据源的旧版本设为非活动；
4. 将新版本设为`ready + active`。

只有全部文档写入成功后才切换活动版本，因此在线检索不会看到一半新、一半旧的Schema。

### 离线步骤P13：配置并认证业务语义层

页面：`/admin/semantic-layer`

管理员根据真实业务制度配置指标、维度、码值集、JOIN、业务规则和Golden Query。每条定义经历`draft → certified → disabled`生命周期，只有`certified`定义会进入正式规划和绑定链路。

例如“医疗总费用”需要明确绑定字段、聚合方式、事实表、时间口径和排除规则；“住院”需要明确对应哪个字段及真实码值。模型只能建议候选，不能自行把建议提升为认证口径。

### 离线步骤P14：形成动态工具环境并做验收

同步成功后，数据源保存当前`schema_version`、`schema_fingerprint`以及可用工具：

```text
search_schema
get_table_detail
lookup_dimension_values
explain_sql
execute_readonly_sql
```

这里的“动态搭建”不是运行时生成任意程序，而是让一组固定且受控的工具绑定到当前数据源、Schema白名单和活动知识版本。上线前至少测试：Schema检索、相似字段消歧、认证指标绑定、JOIN关系、只读执行、成本限制以及若干有权威答案的Golden Query。

### 离线阶段最终产物

```text
可登录的用户
+ 加密的数据源连接配置
+ 可访问Schema白名单
+ 当前Schema指纹和活动版本
+ 表/字段/关系向量文档
+ 安全的低基数字典值
+ 已认证指标、维度、码值和JOIN
+ 已失效查询路径清单
+ 可供在线Agent调用的受控工具集合
```

只有准备出这些产物，下面的在线阶段A、B、C才具备可靠的Schema证据和业务口径。

## 2. 一次查询实际上分成三个HTTP阶段

### 步骤00：认证用户并确定数据归属

登录接口校验用户名和PBKDF2密码哈希，服务端签发带有效期和版本号的HMAC令牌，并写入`HttpOnly` Cookie。后续API不再相信前端传入的`X-User-Id`，而是从签名令牌恢复`tenant_id`、`user_id`和角色。

所有查询会话的创建、列表与详情都使用服务端身份中的`user_id`。因此用户只能访问自己的消息、QueryPlan、SQL执行记录和结果快照；即使猜到其他会话ID，接口也统一返回不存在。管理员可在用户管理页创建、停用、重置用户密码；停用或重置会增加令牌版本，使旧登录态立即失效。

代码入口：`app/auth.py`、`app/api_v1/routes.py`、`app/static/login.html`、`app/static/users-admin.html`。

```text
阶段A：发送消息并生成计划
POST /api/v1/conversations/{id}/messages

阶段B：确认计划
POST /api/v1/conversations/{id}/confirm

阶段C：生成、校验、执行SQL                                      
POST /api/v1/conversations/{id}/execute
```

不能把三个阶段理解成一次请求。用户可以在阶段A重复多轮，直到计划完整，再进入B和C。

---

## 3. 阶段A：用户发送消息

### 步骤A01：浏览器提交消息

前端发送：

```json
{
  "content": "查一下今年各医院的住院费用",
  "base_plan_version": null,
  "data_source_id": "当前选择的数据源ID"
}
```

`base_plan_version`用于多轮并发控制。第一次没有历史计划，因此为空；后续补充需求时带上前端当前看到的计划版本。

### 步骤A02：API路由接收请求

执行位置：

```text
app/api_v1/routes.py
send_message()
```

FastAPI完成请求体校验，读取用户和租户上下文，然后调用：

```python
ConversationService.send_message(...)
```

输出仍使用统一响应结构：`request_id + data + error + meta`。

### 步骤A03：读取会话和最新计划

执行位置：

```text
app/conversation/service.py
ConversationService.send_message()
```

程序先调用Repository：

```text
repository.get()          校验会话存在并属于当前上下文
repository.latest_plan()  读取上一版QueryPlan
```

如果前端提交的`base_plan_version`不是最新版本，抛出计划冲突，防止两个页面同时修改造成覆盖。

### 步骤A04：保存用户消息并形成累计问题

程序调用：

```text
repository.add_message()
repository.messages()
```

第一条用户消息还会成为会话默认标题。随后按照时间顺序拼接全部用户消息，形成`cumulative_question`，用于认证查询路径匹配。

注意：模型本轮修改主要处理当前消息；累计问题主要用于历史路径复用，不能无边界地把全部聊天记录原样发送给模型。

### 步骤A05：确定查询数据源

程序调用：

```text
DataSourceService.ready_source()
```

选择顺序：

1. 本轮显式选择的数据源；
2. 上一版计划继承的数据源；
3. 当前可用的默认数据源。

输出包含数据源ID、Schema指纹、业务规则等公开信息，不把明文密码发给模型或前端。

### 步骤A06：第一次Schema RAG检索

程序调用：

```text
DataSourceService.search(query=当前用户消息, limit=30)
```

内部主要经过：

```text
当前问题生成Embedding
→ pgvector计算向量相似度
→ pg_trgm计算词法相似度
→ 合并得分
→ 返回表、字段和关系候选
```

会话层最多整理24条候选交给规划器，每条包含对象类型、技术键、业务名称、内容摘要、Schema、表、字段、分数和是否需要确认。

这里的输出是“候选Schema”，还不是最终字段绑定。

### 步骤A07：加入认证语义文档

程序调用：

```text
SemanticLayerService.retrieval_documents()
```

已认证的指标、维度、码值和JOIN定义会被放在普通RAG候选之前，帮助模型优先理解企业正式口径。重复对象根据`object_key`去重。

### 步骤A08：读取记忆上下文

程序调用：

```text
MemoryService.context()
```

读取用户偏好、业务记忆等可复用上下文。记忆只能作为辅助信息，不能覆盖用户本轮明确要求，也不能自动升级为认证业务口径。

### 步骤A09：查找认证查询路径

程序调用：

```text
ContextLearningService.context()
ContextLearningService.find_exact_plan()
```

只有同时满足以下条件才直接复用计划：

- 数据源相同；
- 累计问题规范化后匹配；
- 路径已经人工审核认证；
- Schema指纹仍然一致。

复用的是结构化QueryPlan，不是历史裸SQL。后续仍要重新校验Schema并生成SQL。

### 步骤A10：调用百炼生成或修改计划

没有命中认证路径时：

```text
没有上一版计划 → BailianQueryPlanner.create_plan()
存在上一版计划 → BailianQueryPlanner.revise_plan()
```

发送给模型的主要内容：

- 当前用户问题；
- 上一版QueryPlan（修改场景）；
- Schema RAG候选；
- 认证语义和可复用记忆；
- PlanningDraft的JSON Schema；
- 系统约束Prompt。

模型只负责输出JSON计划草稿，不连接数据库、不执行SQL。

### 步骤A11：解析模型JSON

执行位置：

```text
app/planning/bailian.py
BailianQueryPlanner._call()
```

处理过程：

```text
模型返回文本
→ json.loads()
→ PlanningDraft.model_validate()
→ _normalize()
→ QueryPlanV1
```

JSON不符合协议时，把Pydantic错误反馈给模型修正一次；仍然失败则返回`PLANNER_INVALID_OUTPUT`，不会用关键词规则伪装成功。

### 步骤A12：规范化时间和多轮变更

规划器将“今年截至目前”等相对时间转换为实际日期。同比场景同时计算上年同期区间。

修改计划时，模型返回`changed_fields`。程序只接受用户本轮明确修改的部分，没有被修改的指标、维度、条件和时间从上一版恢复，避免计划漂移。

这一阶段的输出才是初步`QueryPlanV1`。

### 步骤A13：写入数据源规则并应用认证定义

会话服务执行：

```text
plan.data_source_id = 当前数据源
plan.default_policies = 数据源认证规则
SemanticLayerService.apply_certified()
```

例如“医保基金支付总额”有认证定义时，正式字段和聚合方式覆盖模型的同名推测。

### 步骤A14：计划程序化修正

会话服务继续执行：

```text
_normalize_explicit_time_binding()
_align_semantics_to_certified_bindings()
_link_filter_values()
_remove_redundant_year_filter()
```

分别处理明确时间字段、SQL语义与认证字段对齐、业务展示值到数据库真实码值绑定，以及删除和日期范围重复的年份过滤。

### 步骤A15：补充Schema证据和字段候选

程序将本次RAG结果写入：

```text
plan.schema_evidence
plan.field_candidates
```

`schema_evidence`用于结果证据链和可信度判断；`field_candidates`用于展示字段候选和后续消歧。

### 步骤A16：检测相似字段歧义

如果候选字段得分接近、被标记为`requires_confirmation`，并且当前计划没有明确绑定其中任何一个，程序加入`field_binding`澄清问题。

例如：

```text
医疗总费用
医保基金支付总额
统筹基金支出
```

都与“住院费用”接近时，系统不直接采用第一名，而是让用户确认。

### 步骤A17：验证字段真实存在和绑定完整

程序调用：

```text
_invalid_schema_bindings()
_missing_semantic_bindings()
```

检查：

- 指标、维度、过滤和时间是否都绑定字段；
- 绑定的表和字段是否存在于当前数据源；
- 字段语义是否适合对应角色；
- 按月查询是否存在时间字段。

### 步骤A18：针对错误绑定进行定向检索和模型修正

存在错误或缺失绑定时，系统不会直接把整个流程推倒重来，而是根据问题重新检索相关字段，组成`correction_context`，再调用`revise_plan()`。

修正Prompt明确要求：只修改错误绑定，不得改变用户已确认的指标、时间、比较及其他需求。

修正后再次执行绑定完整性检查。仍失败则加入`schema_binding_invalid`澄清问题，阻止执行。

### 步骤A19：决定计划状态

```text
存在澄清问题 → clarifying
计划完整       → awaiting_confirmation
```

此时还没有生成SQL。

### 步骤A20：保存不可变计划版本

程序调用：

```text
ConversationRepository.save_plan()
```

内部执行：

- 计划版本号加1；
- 保存完整QueryPlan JSON；
- 使用`stable_hash()`计算计划哈希；
- 更新会话当前版本和状态。

如果启用记忆服务，同时保存本轮会话摘要。

### 步骤A21：生成面向用户的回复

`conversation_reply()`根据计划状态生成：

- 澄清问题和选项；或
- “我理解的最终需求”计划摘要。

助手消息写入数据库，API返回计划、版本、哈希、状态、Schema证据和是否复用认证路径。前端据此更新左侧聊天和右侧计划表。

---

## 4. 多轮补充如何循环

用户回答“医疗总费用”时，再次从A01进入，但此时：

- `base_plan_version`携带上一版本；
- `latest_plan`不为空；
- 规划器调用`revise_plan()`而不是`create_plan()`；
- 只允许修改本轮涉及的指标及澄清内容；
- 医院维度和今年时间范围继续保留。

用户再回答“按结算日期统计”时重复同样过程，补齐时间字段绑定。直到`plan.needs_clarification == false`，状态变为`awaiting_confirmation`。

---

## 5. 阶段B：用户确认QueryPlan

### 步骤B01：前端提交确认

```json
{
  "plan_version": 3,
  "plan_hash": "64位SHA-256哈希"
}
```

### 步骤B02：校验身份上下文与最新版本

API调用：

```text
ConversationService.confirm()
→ repository.get()
→ repository.confirm()
```

Repository检查：

- 提交版本是否为会话最新版本；
- 数据库保存哈希是否与提交哈希一致；
- 计划是否仍存在待澄清问题。

任何一项失败都拒绝确认。

### 步骤B03：记录确认观察

确认成功后调用：

```text
SemanticLayerService.observe_confirmation()
```

它只记录用户采用了哪些字段，用于统计和发现候选业务口径，不会自动把用户选择升级为`certified`。

输出状态为`confirmed`。此时仍未执行SQL。

---

## 6. 阶段C：生成并执行SQL

### 步骤C01：校验只能执行最新确认计划

执行入口：

```text
ConversationService.execute()
```

程序再次读取最新计划，要求：

- 版本与请求一致；
- 状态为`confirmed`；
- 计划属于当前会话和用户上下文。

随后创建状态为`executing`的执行记录对象。

### 步骤C02：解密数据源连接配置

程序调用：

```text
DataSourceService.connection_profile()
```

只有执行服务在需要连接数据库时解密密码。密码不会出现在API响应、QueryPlan、RAG文档或模型Prompt中。

### 步骤C03：进入Text-to-SQL执行引擎

程序调用：

```text
PostgresTextToSqlEngine.execute_plan(plan, source_profile)
```

执行引擎生成`query_id`并开始记录总耗时。

### 步骤C04：运行时再次获取SchemaContext

程序调用：

```text
PostgresSchemaRetriever.retrieve()
```

这里会基于已确认计划再次读取/筛选真实目录和表关系，形成只属于本次执行的`SchemaContext`，其中包含：

- 允许使用的表；
- 每张表允许使用的字段；
- 已验证的外键或JOIN关系；
- 提供给SQL生成器的Schema描述。

这样即使需求分析到执行之间Schema发生变化，也不会仅依赖旧的模型上下文。

### 步骤C05：Capability Router选择生成路径

程序调用：

```text
CapabilityRouter.decide(plan, context)
```

Router不是让模型判断，而是按固定顺序检查：

```text
1. 计划仍有澄清项               → clarify
2. 意图被标记为unsupported       → reject
3. 指标/维度/过滤/时间绑定缺失    → clarify
4. 表或字段不在运行时Schema       → resync_schema
5. 指标聚合口径缺失或不受支持     → clarify
6. 环比没有与粒度一致的时间维度   → clarify
7. 同比没有完整同期范围          → clarify
8. 多表但不存在认证的连通JOIN路径 → clarify
9. 编译器完整支持全部操作         → deterministic
10. 语义完整但表达组合超出覆盖    → model_fallback
```

返回值是结构化`RouteDecision`，包含`route`、`reason_code`、所需能力、不支持能力、缺失项、风险和可选的编译结果。例如：

```json
{
  "route": "deterministic",
  "reason_code": "SUPPORTED_BY_DETERMINISTIC_COMPILER",
  "required_capabilities": ["aggregate_analysis", "filter", "group_by", "year_over_year"],
  "unsupported_capabilities": [],
  "missing": [],
  "risks": []
}
```

`clarify`、`reject`和`resync_schema`不会调用Qwen生成SQL，而是保留计划并返回稳定错误码。只有`deterministic`和`model_fallback`可以继续进入SQL生成阶段。路由结果还会写入`capability_routed`事件和查询证据链。

当前权限和患者敏感数据策略仍属于Router之前的安全门禁；基础登录不能替代行列级授权。

### 步骤C05A：确定性能力匹配

Router内部调用`DeterministicQueryCompiler.compile(plan, context)`。当前确定性子集包括：单事实表、已绑定多指标、SUM/COUNT/COUNT DISTINCT/AVG/MIN/MAX、普通维度、自然日/ISO周/自然月/自然季度/自然年、过滤、这些自然粒度的同比和环比、期间累计同比、全局排序和Top-N。

编译器采用“无法完整表达就失败”的原则：未知聚合不会退化成裸字段；环比缺少对应时间维度不会静默退化成普通查询；滚动7天、财务季度、自定义结算周期等业务日历必须先澄清。

### 步骤C06A：确定性编译器生成SQL

确定性路径按固定顺序将QueryPlan转换为：

```text
指标绑定 → SUM/COUNT/AVG等表达式
维度绑定 → SELECT和GROUP BY
过滤绑定 → WHERE
日期范围 → 左闭右开的时间条件
同比/环比 → CTE、同期关联和增长率
排名要求 → ORDER BY和LIMIT
```

相同QueryPlan会产生相同SQL，不再调用大模型写SQL。

### 步骤C06B：模型生成候选SQL

只有Router确认“业务语义和字段绑定完整，但表达能力超出确定性子集”时才调用：

```text
BailianSqlGenerator.generate_candidates()
```

模型只接收已确认QueryPlan和本次SchemaContext，可以生成多个候选。它没有数据库连接权限，也不能使用候选范围之外的表字段。

### 步骤C07：逐条执行SQLGlot校验

程序调用：

```text
PostgresSqlValidator.validate(candidate_sql, context, plan)
```

检查：

1. PostgreSQL语法能否解析。
2. 是否只有一条SELECT/WITH。
3. 是否包含DDL或DML。
4. 表和字段是否来自Schema白名单。
5. 字段是否属于正确的表。
6. 输出、聚合、过滤、分组、排序是否与QueryPlan一致。
7. 时间范围、同比方向和增长率公式是否正确。

每个候选的错误和告警都写入执行事件。

### 步骤C08：选择合法候选或有限修正

存在多个合法候选时，按照：

```text
校验告警最少
→ 原候选顺序靠前
```

选择一个SQL。

模型候选全部失败时，将去重后的校验错误作为`correction`反馈给模型，最多3轮。确定性SQL只有一个固定候选，校验失败直接暴露编译器一致性错误，不使用模型掩盖。

### 步骤C09：建立业务数据库连接

SQL通过静态校验后才建立执行连接。连接失败、密码错误和权限错误被分类为不可由模型修复的基础设施问题。

### 步骤C10：进入只读事务并设置超时

```text
connection.transaction(readonly=True)
SET LOCAL statement_timeout
```

应用层只读校验和数据库只读事务是两道独立防线；生产环境还必须使用真正的只读数据库账号。

### 步骤C11：包装最大行数

原SQL被包装成：

```sql
SELECT * FROM (
  原始SQL
) AS sqlpilot_bounded
LIMIT max_rows + 1
```

多取一行用于判断结果是否被截断，真正返回用户时最多保留`max_rows`行。

### 步骤C12：EXPLAIN成本检查

执行：

```sql
EXPLAIN (FORMAT JSON) 包装后的SQL
```

解析`Plan Rows`和`Total Cost`。超过配置阈值时抛出`QUERY_COST_EXCEEDED`，不会执行正式查询。

### 步骤C13：执行只读SQL

成本允许后执行查询，将asyncpg Record转换为字典列表。记录是否截断、实际返回行数和包装后的SQL。

### 步骤C14：处理数据库执行错误

确定性SQL执行失败：返回`SQL_COMPILER_EXECUTION_FAILED`，提示检查编译器或环境。

模型SQL执行失败：

- 可修复语法/字段类错误：把截断后的安全错误反馈给模型；
- 最多执行修正2次；
- 密码、权限、连接拒绝等错误不重试；
- 超限后保留QueryPlan并返回建议，不伪造结果。

### 步骤C15：序列化并做结果合理性检查

结果中的日期、Decimal等对象转换为JSON可序列化值。随后检查：

- 是否为空结果；
- 要求多维或按月时是否只返回一行；
- 高置信计划的输出字段是否缺失。

这些检查产生告警，不修改数据库结果。

### 步骤C16：生成中文结果Schema

程序调用：

```text
build_result_schema()
```

根据SQL别名和字段规则生成中文标题、文本/日期/金额/人次/百分比类型及单位。原始SQL字段和值不被改写，展示元数据单独返回。

### 步骤C17：生成图表配置

程序调用：

```text
build_chart_spec()
```

处理原则：

- 时间维度 + 数值 → 折线图；
- 分类维度 + 数值 → 柱状图；
- 金额、人次、比例按量纲拆分；
- 同量纲最多组合若干指标；
- 限制图表点数并标记是否截断。

返回的是图表JSON配置，前端负责渲染。

### 步骤C18：生成AI数据解读

程序调用：

```text
ResultInterpreter.interpret()
```

当前实现向百炼提供确认计划、结果字段说明、行数、最多前50行结果、图表配置和截断状态，要求输出`summary/findings/caveats`。

模型失败时使用本地fallback摘要，不影响表格结果。

安全边界：当前做法只适合测试环境的聚合数据。生产环境必须增加模型数据出口网关，患者级明细和敏感字段不得发送给外部模型。

### 步骤C19：计算可信等级和证据链

执行引擎根据以下因素计算A-D等级：

- Schema证据分数；
- 是否仍有未消歧字段；
- 多表查询是否存在验证关系；
- SQL生成校验修正次数；
- 数据库执行修正次数。

证据链同时记录数据源、使用表、Schema策略、SQL生成策略、只读状态、EXPLAIN成本和事件列表。

可信等级表示技术证据完整程度，不代表业务结果百分之百正确。

### 步骤C20：保存完整执行快照

返回`ConversationService.execute()`后，执行状态改为`completed`，保存：

- 最终SQL；
- 原始结果；
- 中文结果Schema；
- 图表配置；
- AI解读；
- 校验结果；
- 可信等级；
- 证据和事件。

这样历史查询打开时可以恢复当时看到的完整结果，而不是重新执行SQL。

执行失败时保存失败状态、错误码和去敏详情。

### 步骤C21：前端呈现

前端收到结果后依次展示：

1. 查询可信等级和告警；
2. AI数据摘要；
3. 图表；
4. 中文结果表格；
5. SQL及Schema证据等技术详情。

---

## 7. 阶段D：用户反馈与查询路径学习

用户点击“结果正确”后，系统根据已完成执行记录创建待审核反馈。管理员审核结果、计划、字段和Schema指纹：

- 审核通过：生成`certified`查询路径；
- 审核拒绝：反馈和路径停用；
- Schema改变：相关路径变为`stale`。

下一次相同累计需求可以在A09命中并复用计划，但仍从C04开始重新检查Schema、生成SQL并执行全部安全门禁。

## 8. 患者敏感数据门禁应该插在哪里

以下是产品设计要求，当前代码尚未完整实现：

```text
A11模型计划草稿之后
→ 检查是否为患者级意图

A15字段绑定之后
→ 检查是否绑定L3/L4敏感字段

C07 SQL AST校验时
→ 检查实际SELECT、WHERE、JOIN和查询粒度

C15结果返回之前
→ 检查敏感格式、小样本和模型出域
```

当前已有用户登录、基础角色和会话归属隔离，但尚无患者关系、业务用途及行列级授权，因此患者明细、身份信息和病历内容仍应采用默认拒绝策略。

## 9. 主调用链速记

```text
routes.send_message
→ ConversationService.send_message
→ DataSourceService.search
→ MemoryService.context
→ ContextLearningService.find_exact_plan
→ BailianQueryPlanner.create_plan/revise_plan
→ Pydantic PlanningDraft/QueryPlanV1
→ SemanticLayerService.apply_certified
→ link_fields + binding validation
→ ConversationRepository.save_plan

routes.confirm_plan
→ ConversationService.confirm
→ ConversationRepository.confirm
→ SemanticLayerService.observe_confirmation

routes.execute_plan
→ ConversationService.execute
→ PostgresTextToSqlEngine.execute_plan
→ PostgresSchemaRetriever.retrieve
→ DeterministicQueryCompiler.compile
   或 BailianSqlGenerator.generate_candidates
→ PostgresSqlValidator.validate
→ EXPLAIN
→ readonly transaction execute
→ build_result_schema
→ build_chart_spec
→ ResultInterpreter.interpret
→ ConversationRepository.save_execution
```

## 10. 学习时每一步只回答五个问题

阅读代码或面试讲解时，对每个节点固定回答：

1. 输入是什么？
2. 调用了哪个类或函数？
3. 内部做了什么判断？
4. 输出保存到哪里？
5. 失败后怎么处理？

只要能顺着本文件完整回答这五个问题，就已经能够清楚讲出整个SQLPilot项目，而不需要背每一行代码。
