# SQLPilot 完整项目实现说明

## 1. 项目定位

SQLPilot 是一个面向医保数据分析的可信 Text-to-SQL 产品。它允许非技术业务人员使用中文多轮描述查询需求，并在执行前查看、修改和确认最终统计计划。

项目的核心判断是：**SQL 能执行不代表业务结果可信**。真正影响客户使用价值的是：指标口径是否正确、字段是否绑定正确、JOIN 是否导致重复聚合、时间和过滤条件是否完整，以及结果是否能够被解释和追溯。

因此系统不是“问题直接交给大模型生成 SQL”，而采用以下分层：

```text
业务人员中文对话
  -> 百炼模型生成强类型 QueryPlan
  -> 认证语义层覆盖正式业务口径
  -> 动态 Schema RAG 完成字段绑定
  -> 字段歧义时追问
  -> 用户确认计划版本和哈希
  -> 确定性编译器优先 / 模型候选 SQL 兜底
  -> SQLGlot AST + 计划一致性校验
  -> EXPLAIN 成本检查
  -> PostgreSQL 只读事务执行
  -> 中文字段、图表、AI 数据解读、可信证据链
  -> 用户反馈、管理员审核、认证路径复用
```

## 2. 技术栈与真实边界

| 层次 | 技术 |
|---|---|
| Web/API | FastAPI、HTML/CSS/JavaScript |
| 需求理解 | 阿里云百炼兼容 OpenAI API、Qwen、Pydantic JSON Schema |
| Embedding | DashScope `text-embedding-v4`，默认 1,024 维 |
| 数据库 | PostgreSQL、SQLite 系统库、SQLAlchemy Async、asyncpg |
| 向量检索 | pgvector 余弦距离 + pg_trgm 词法相似度 |
| SQL | PostgreSQL、SQLGlot AST、确定性编译器、模型候选兜底 |
| 部署 | Docker Compose；原 Conda 环境可用于开发测试 |
| 评测 | Pytest、Spider 1.0 Execution Accuracy、自建失败根因分析 |

当前没有把 Neo4j、Milvus 和 LangGraph 放进正式运行链路。关系数据规模目前适合直接保存在关系型数据库中；只有当跨域关系、路径规则和图算法复杂度明显增加时，才值得引入 Neo4j。

## 3. 代码目录

```text
app/main.py                         应用装配、路由和管理页面
app/auth.py                         登录、密码哈希、令牌、角色和用户管理
app/api_v1/                         REST API 与请求协议
app/conversation/                   会话、消息、计划版本、执行记录和状态机
app/planning/                       QueryPlan、百炼规划器、Prompt 和摘要
app/data_sources.py                 数据源管理、Schema 扫描、后台同步
app/knowledge_store.py              pgvector 写入、Embedding、混合检索
app/semantic_layer.py               认证指标/维度/码值/JOIN 语义层
app/schema_linking.py               字段候选与 Value Linking
app/context_learning.py             反馈审核、认证查询路径和依赖图
app/memory.py                       会话摘要、用户偏好和业务记忆
app/text_to_sql/schema.py           运行时 Schema 上下文与外键关系
app/text_to_sql/compiler.py         确定性 SQL 编译器
app/text_to_sql/generator.py        百炼 SQL 候选生成
app/text_to_sql/validator.py        SQLGlot AST 与业务一致性校验
app/text_to_sql/engine.py           生成、校验、成本控制、执行和重试
app/text_to_sql/presentation.py     中文列名、字段类型和单位
app/text_to_sql/insights.py         图表选择和 AI 数据解读
app/benchmarks/                     Spider 数据集和执行结果评测
app/static/                         主界面与管理界面
tests/                              102 项自动化测试
```

## 4. 数据源接入与动态环境搭建

### 4.1 用户配置什么

用户在数据源管理页面填写 PostgreSQL 主机、端口、库名、用户名、密码和允许访问的 Schema。密码通过 Fernet 加密后保存，密钥由 `SQLPILOT_SECRET_KEY` 提供；未单独配置时开发环境回退使用 DashScope Key 派生，但生产环境必须使用独立密钥。

数据源账号应只授予目标 Schema 的 SELECT 权限，不应授予 DDL/DML 权限。

### 4.2 连接测试

系统使用 asyncpg 建立连接，读取数据库版本并验证事务默认只读状态。连接配置不会直接传入 Prompt。

### 4.3 后台 Schema 同步

`POST /api/v1/data-sources/{id}/sync` 先创建 `SchemaSyncJobRecord`，然后由 FastAPI BackgroundTasks 执行同步。阶段包括：

1. `queued`：任务排队。
2. `connecting`：连接业务库。
3. `catalog_scanned`：读取表字段和外键。
4. `embedding`：生成向量。
5. `activating`：切换知识版本。
6. `ready`：同步完成。

同一数据源已有 queued/running 任务时返回 duplicate，避免重复构建。

注意：当前 BackgroundTasks 适合单机版。生产多实例应替换为 Celery/RQ/Arq 等持久任务队列，否则进程重启会中断任务。

### 4.4 扫描内容

系统查询 `information_schema.columns`、`pg_class`、`pg_namespace` 和 `pg_attribute`，获取：

- Schema、表名、字段名、顺序和数据类型；
- 表注释、字段注释、是否可空；
- PostgreSQL 外键及两端字段；
- 适合做维度的低基数字段样本值。

用户在 Schema 管理页面填写的中文显示名、业务描述、别名和启停状态会与数据库元数据合并。

## 5. Schema RAG 如何构建

### 5.1 为什么按字段构建向量

只按整张表构建向量时，一张大表包含上百个字段，目标字段语义会被其他内容稀释。SQLPilot 采用“表文档 + 字段文档 + 关系文档”三级文档，但字段文档是 Schema Linking 的主要粒度。

### 5.2 字段文档格式

每个字段独立拼接：

```text
Schema nhsa；
表名 setl_d；
表注释 医保结算主表；
字段名 fund_pay_sumamt；
字段类型 numeric；
字段注释与业务别名 基金支付总额、医保基金支付金额；
低基数字典值 ...
```

这就是简历中“表名 + 表注释 + 字段名 + 字段注释 + 字典值”的真实实现，同时额外加入 Schema、字段类型、人工别名和业务描述。

字典值只加入低基数字段，避免把身份证号、结算号等高基数敏感值大量写入知识库。

### 5.3 表文档

表文档包含表的业务名称、描述、别名、数据库注释以及所有启用字段的简要说明，用于先识别主题表。

### 5.4 关系文档

外键生成独立关系文档：

```text
表关系：fee_list_d.setl_id 关联 setl_d.setl_id
```

运行时 Schema Retriever 还会读取真实外键，使用桥接表算法扩展连接路径。

### 5.5 版本和原子切换

数据库原始元数据和人工业务元数据进行 canonical JSON 序列化，计算 SHA-256 指纹。每次同步创建新版本，所有新文档和向量写完后才把新版本设为 active，并关闭旧版本，避免用户检索到半成品索引。

### 5.6 Embedding

`PgVectorKnowledgeStore.embed()` 按批次调用百炼 Embedding 接口，默认模型 `text-embedding-v4`、维度 1,024、每批最多 10 条。返回向量按接口 index 排序，保证与输入文档一一对应。

### 5.7 混合检索

查询向量与文档向量使用 pgvector 余弦距离 `<=>`，文本关键词使用 pg_trgm `similarity()`：

```text
最终得分 = 0.7 × vector_score + 0.3 × lexical_score
```

向量负责中文业务语义，词法分数负责表名、字段名、缩写和代码的精确匹配。

若前两个字段候选得分差小于 0.02，系统将接近最高分的一组字段标记为 `requires_confirmation`，对话层生成“采用哪个业务口径”的结构化澄清选项，而不是强行 Top-1。

## 6. 需求理解与多轮对话

### 6.1 为什么不让模型直接生成 SQL

直接生成 SQL 无法让业务人员确认“系统究竟理解成了什么”，也难以判断修正是否偷偷改变指标。SQLPilot 先让模型生成强类型 QueryPlan。

### 6.2 QueryPlan 字段

- `intent`：汇总分析、明细查询或不支持。
- `metrics`：最多 3 个指标。
- `dimensions`：机构、月份等维度。
- `date_range`：当前年至今、上年、明确范围或全部。
- `filters`：字段、操作符、真实值和展示值。
- `comparison`：无、环比、同比和比较粒度。
- `ranking`：排名指标、方向、范围和 Top-N。
- `clarifications`：结构化追问。
- `semantic_bindings`：指标/维度/过滤/时间与真实字段绑定。
- `semantics`：输出列、粒度、聚合、去重、HAVING、排序和集合逻辑。
- `schema_evidence`：RAG 证据及分数。
- `provenance`：模型、Prompt 版本和目录版本。

Pydantic 使用 `extra="forbid"`，模型不能随意增加协议外字段。

### 6.3 模型调用

规划器使用 OpenAI 兼容客户端连接百炼，temperature=0、关闭 thinking，要求 JSON Object。PlanningDraft 的 JSON Schema 动态注入 Prompt。

模型输出若无法通过 JSON/Pydantic 校验，系统把具体校验错误反馈给模型修正一次；仍失败则明确返回 `PLANNER_INVALID_OUTPUT`，不会降级成关键词规则冒充模型。

### 6.4 多轮变更保护

模型修改已有计划时必须返回 `changed_fields`。系统只接受用户本轮明确涉及的顶层字段，未列出的指标、维度和过滤会恢复上一版，防止用户只说“按年度汇总”时模型误删“医疗机构”等已有条件。

每次对话保存新计划版本；确认时同时校验 `plan_version` 和 `stable_hash`。计划一旦发生变化，旧确认不能继续执行。

### 6.5 追问机制

以下情况会阻止执行并追问：

- 指标、时间字段或维度缺少真实绑定；
- 过滤意图存在但没有数据库实际值；
- 多个字段语义分数接近且认证语义层无法消歧；
- 排名范围不明确，例如“增长较高的月份”没有说明逐机构还是总体。

## 7. 认证语义层

认证语义层保存 `metric`、`dimension`、`value_set`、`join`、`business_rule` 和 `golden_query`。

状态：

- `draft`：草稿，不影响查询；
- `certified`：正式口径，优先覆盖模型/RAG；
- `disabled`：停用。

例如：

```json
{
  "kind": "metric",
  "semantic_key": "fund_pay_total",
  "label": "医保基金支付总额",
  "definition": {
    "object_key": "nhsa.setl_d.fund_pay_sumamt",
    "aggregation": "sum",
    "unit": "元"
  },
  "status": "certified"
}
```

应用计划时，认证定义优先替换模型选择的同名 binding。用户确认只写入 observation，不会自动变为正式口径，避免错误选择污染知识库。

## 8. 查询路径学习闭环

用户在执行结果下点击“结果正确”或“反馈问题”。正确反馈必须来自 completed execution，系统读取当时的 QueryPlan、用户问题、数据源指纹和字段依赖，生成 draft 查询路径。

管理员在学习中心检查结果、业务口径和字段绑定后：

- 审核通过：状态变为 certified；
- 驳回：状态变为 disabled；
- Schema 指纹变化：状态自动变为 stale。

后续多轮对话会把全部用户消息按顺序拼成累计需求。只有规范化问题完全匹配、数据源相同、路径 certified 且 Schema 指纹相同时，才直接复用结构化 QueryPlan。

复用的不是历史裸 SQL。系统仍会重新应用认证语义层、校验当前 Schema、编译 SQL、执行 AST 安全检查和成本检查。

## 9. SQL 生成双通道

生成前先由`CapabilityRouter`返回结构化路由决策，而不是把编译器所有`None`都交给模型。路由结果包括`deterministic`、`model_fallback`、`clarify`、`reject`和`resync_schema`。

缺少指标、维度、过滤、时间或聚合绑定时返回澄清；绑定对象不属于当前Schema时要求重新同步；多表查询缺少认证JOIN路径时阻止生成。只有语义绑定完整、Schema真实存在、必要JOIN路径已验证，但表达组合超出确定性能力时，才允许模型兜底。路由原因和能力差异会进入执行事件与证据链。

### 9.1 确定性编译器优先

`DeterministicQueryCompiler` 支持：

- 单事实表；
- 多指标 SUM/COUNT/COUNT DISTINCT/AVG/MIN/MAX；
- 普通维度，以及自然日、ISO周、自然月、自然季度、自然年；
- 上述自然粒度的同比和环比，以及期间累计同比；
- 行级过滤、认证默认规则；
- 排序和 Top-N。

同比通过 current_data 和 year_ago_data 两个 CTE 按维度连接，增长率使用：

```sql
(current_value - previous_value) * 100.0 / NULLIF(previous_value, 0)
```

环比先额外读取一个前置周期，再使用`LAG`按其他维度分区、按时间粒度排序；外层结果会过滤掉仅用于计算的前置周期，保证首个展示周期也能得到正确环比。周粒度按周一开始的ISO自然周处理。

以下场景不进入确定性时间比较：滚动7天/30天、财务季度、医保自定义结算周期、4-4-5财务日历以及未明确周期边界的“上一周期”。这类需求必须先由用户或业务语义层确认日历口径；确认后若仍超出编译器操作符范围，再进入模型兜底。

确定性路径的优势是相同计划始终产生相同 SQL，易测试、易审计，模型不会临时改变业务逻辑。

### 9.2 模型 SQL 受控兜底

多表、集合运算、复杂 HAVING 等编译器暂不覆盖的查询进入 `bailian_sql_fallback`。模型获得的上下文只有已检索 Schema、认证绑定、关系和已确认 QueryPlan。

每一轮可生成多个候选 SQL，所有候选分别校验。通过的候选按“告警最少、原模型顺序优先”选择。全部失败时把去重后的校验错误反馈给模型，最多生成/修正 3 轮。

## 10. SQL 校验细节

### 10.1 语法和只读

SQLGlot 以 PostgreSQL 方言解析 AST：

- 只允许一条语句；
- 必须包含 SELECT；
- 禁止 INSERT、UPDATE、DELETE、CREATE、DROP、ALTER、Command；
- CTE 名称与真实物理表分开处理。

### 10.2 Schema 白名单

- 每个物理表必须唯一命中 SchemaContext；
- 所有列必须存在于允许字段集合；
- 有表别名的字段必须属于对应表；
- CTE 输出别名不误判为物理字段。

### 10.3 计划一致性

- SQL 必须输出计划中的每个指标别名；
- 开始和结束日期必须出现；
- 过滤字段和过滤值必须出现；
- 未要求同比时不得擅自增加同比；
- 未要求业务排名时只能按已确认维度做展示排序；
- output_fields 数量、别名和顺序必须与语义计划一致；
- 要求 GROUP BY、DISTINCT、HAVING、ORDER BY、UNION/INTERSECT/EXCEPT/NOT EXISTS 时 SQL 必须实现。

### 10.4 时间与同比专项

- 时间戳使用 `[start, next_day)` 半开区间，禁止拼 `23:59:59`；
- 同比月份连接方向不能写反；
- 增长率必须乘 100；
- `NULLIF` 必须作用于上期值，不能作用于差额；
- 当前期和同期日期范围必须完整出现。

## 11. 执行安全与失败处理

1. SQL 外层包装 `LIMIT max_rows + 1`，用于判断是否截断；默认最多返回 500 行。
2. 开启 PostgreSQL readonly transaction。
3. `SET LOCAL statement_timeout`，默认 15 秒。
4. 执行 `EXPLAIN (FORMAT JSON)`，读取 Plan Rows 和 Total Cost。
5. 超过配置的预计行数或成本时返回 `QUERY_COST_EXCEEDED`，不执行正式查询。
6. 执行错误仅在模型兜底路径修正，最多 2 次；密码、权限、连接拒绝等不可修复错误不重试。
7. 超出重试次数后保留 QueryPlan，返回错误原因和“补充口径、同步 Schema、稍后重试”等建议，不向用户伪造结果。

确定性编译 SQL 若执行失败不会让模型改写，因为这通常意味着编译器或环境错误，应暴露并修复根因。

## 12. 结果展示

### 12.1 中文列名与类型

`presentation.py` 根据固定业务元数据和列名模式生成：

- 中文 label；
- text/date/integer/decimal/currency/percentage 类型；
- 元、人次、% 等单位。

### 12.2 多指标图表

图表不是简单“一张表配一张柱状图”。系统先识别类别字段、时间字段和数值字段，再按量纲分组：

- 时间 + 数值：优先折线图；
- 类别 + 数值：柱状图；
- 金额、人次、比例等不同量纲拆成不同图表；
- 多个同量纲指标可以组成多序列图表；
- 限制展示点数并标记是否截断。

### 12.3 AI 数据解读

模型只接收真实查询结果、字段说明、图表配置和截断信息，输出：

- summary；
- findings；
- caveats。

模型失败时使用本地 fallback 生成最基础摘要，不能影响原始查询结果展示。

## 13. 可信度与证据链

结果包含：

- Schema 检索策略和实际表；
- SQL 生成策略（确定性或模型兜底）；
- SQL 校验通过项和告警；
- EXPLAIN 预计行数和成本；
- SQL 生成修正次数和执行修正次数；
- 数据源、只读状态、JOIN 路径；
- A/B/C/D 可信等级和风险列表。

降分因素包括低 Schema 证据、未消歧字段、多表但无验证关系、SQL 校验修正和执行修正。A级不代表业务结果 100% 正确，只代表技术证据完整；正式业务认证仍需 Golden Set 对账。

## 14. 持久化模型

SQLite 系统库当前保存：

- users：账号、密码哈希、角色、状态和令牌版本；
- conversations：会话；
- messages：聊天消息；
- plan_versions：不可变计划和哈希；
- query_executions：SQL、结果、状态和错误；
- data_sources：加密连接配置和 Schema 指纹；
- schema_sync_jobs：同步进度；
- semantic_definitions：认证语义；
- semantic_binding_observations：用户确认观察；
- conversation_memories、user_preferences、business_memories：记忆；
- verified_query_paths、query_feedback：审核式学习闭环。

pgvector 知识库保存 Schema 版本和向量文档。业务数据始终留在客户 PostgreSQL 中。

## 15. API 主流程

认证与用户管理：

```text
POST  /api/v1/auth/login
POST  /api/v1/auth/logout
GET   /api/v1/auth/me
POST  /api/v1/auth/change-password
GET   /api/v1/users
POST  /api/v1/users
PATCH /api/v1/users/{id}
```

登录成功后，服务端签发HMAC令牌并写入HttpOnly Cookie。查询接口只使用令牌中的服务端身份，不信任前端传入的用户编号。`conversations`记录创建时绑定当前`user_id`，读取时同时校验`tenant_id + user_id + conversation_id`；其他用户即使知道会话ID也返回404。

```text
POST /api/v1/conversations
POST /api/v1/conversations/{id}/messages
POST /api/v1/conversations/{id}/confirm
POST /api/v1/conversations/{id}/execute
GET  /api/v1/conversations/{id}
```

数据源与知识库：

```text
POST /api/v1/data-sources
POST /api/v1/data-sources/{id}/test
POST /api/v1/data-sources/{id}/sync
GET  /api/v1/data-sources/{id}/sync/latest
GET  /api/v1/data-sources/{id}/knowledge/search
```

审核学习：

```text
POST /api/v1/query-executions/{id}/feedback
GET  /api/v1/learning/feedback
POST /api/v1/learning/feedback/{id}/review
GET  /api/v1/learning/query-paths
GET  /api/v1/data-sources/{id}/knowledge/dependency-graph
```

## 16. 测试和评测

### 16.1 自动化测试

自动化测试覆盖登录鉴权、跨用户会话隔离、API、状态机、模型规划协议、多指标计划、Schema Linking、语义层、确定性编译、AST 校验、执行引擎、结果图表、AI 解读、学习闭环、管理页面和 Spider 评测工具。

### 16.2 Spider 1.0

最终全量报告（2026-08-29）：

| 指标 | 结果 |
|---|---:|
| 样本数 | 1,034 |
| QueryPlan 表召回 | 98.65% |
| SQL 校验通过 | 100.00% |
| SQL 执行成功 | 100.00% |
| 结果一致 EX | 88.10%（911/1,034） |

主要剩余错误：字段语义 43、聚合 15、DISTINCT 14、表选择 12、JOIN 9、表达式语义 8、集合运算 7、投影 7。

Spider 验证跨域 SQL 能力，但不包含医保正式业务口径。生产验收还需要客户 Golden Set：由业务专家给出问题、口径、期望结果或权威报表，以结果对账一致率为最终指标。

## 17. 部署

当前 Windows 主机的 Conda 原生 DLL 被应用控制策略拦截，因此正式本地演示使用 Docker Compose：

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f sqlpilot
```

容器读取 `.env`、`.env.database.local`、`.env.knowledge.local`，通过 `host.docker.internal` 连接主机 PostgreSQL，挂载 `./data:/app/data` 保留系统库和评测报告。

当前已实现本地账号登录、管理员/分析人员基础角色、用户启停、密码重置和查询会话归属隔离。生产仍需完成：独立 Secret 托管、HTTPS、登录防暴力破解、CSRF防护、细粒度RBAC、数据范围与行列级权限、多租户强隔离、持久任务队列、审计日志归档、备份恢复和监控告警。

## 18. 面试常见追问

### 为什么不用模型直接生成 SQL？

因为无法在执行前确认业务语义，模型修正时也可能偷偷改变指标。QueryPlan 把自然语言理解结果变成可以展示、版本化、校验和复用的中间表示。

### 为什么字段级向量优于整表向量？

整表字段过多会稀释目标字段语义；字段级文档能精确召回，表信息又作为上下文保留。表文档负责主题召回，字段文档负责绑定，关系文档负责 JOIN。

### 为什么还要词法检索？

向量擅长“基金支付金额”和“医保基金支出”这种语义近似，词法检索擅长 `fund_pay_sumamt`、缩写和编码。二者互补。

### 两个字段很像怎么办？

不强制 Top-1。分差小于 0.02 时返回候选，由认证语义层优先消歧；没有认证口径则让用户确认。

### 为什么不用 Neo4j？

当前表关系数量和查询深度使用外键图与 BFS 桥接即可，Neo4j 会增加部署和一致性成本。当关系跨多个业务域、需要复杂路径规则、基数/时效/权限传播或图算法时再引入。

### 确定性编译和模型生成如何分工？

高频、标准、可形式化的查询用编译器，保证可复现；复杂长尾用模型兜底，提高覆盖率。两条路径共用相同 Schema 白名单、安全校验和成本控制。

### SQL 修正为什么有限制？

无限重试浪费 Token，也可能越修越偏。生成校验最多 3 轮、执行错误最多 2 轮，且错误信息经过截断，Prompt 明确不得改变已确认计划。

### 准确率 88.10% 怎么算？

在 Spider 1.0 dev 全量 1,034 条上分别执行预测 SQL 和标准 SQL，将结果集规范化后比较，不是字符串完全匹配。911 条结果一致，所以 EX 为 88.10%。

### 客户为什么能信任？

不能承诺 100%。产品价值来自“风险可见、过程可控、错误可拦截”：认证口径、计划确认、只读执行、证据链、可信等级、人工审核和 Golden Set 对账共同降低错误使用概率。

## 19. 下一步路线

1. 建设 100-300 条医保 Golden Set，按指标、维度、过滤、同比、JOIN 和异常场景分层。
2. 把 Schema 同步迁移到持久任务队列。
3. 为认证语义定义增加生效范围、负责人、版本、审批流和回滚。
4. 扩展确定性编译器对多事实表、窗口函数、集合运算和复杂 HAVING 的覆盖。
5. 增加执行结果漂移监控和定期对账。
6. 当关系复杂度达到阈值后，再评估 Neo4j 图路径规划。
