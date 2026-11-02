# SQLPilot

SQLPilot 是一个面向医保数据分析的可信 Text-to-SQL 应用。生产查询理解通过企业百炼模型生成受约束的结构化 QueryPlan；程序负责认证目录校验、澄清、确认、SQL生成、安全执行与证据链。

## 当前能力

- 认证指标：基金支付总额、总费用、结算人次
- 查询理解：指标、维度、年度、Top-N、环比、机构等级
- Value Linking：例如“三甲”映射为机构等级编码 `3A`
- 受控关系：只允许使用已验证的 `settlement -> medical_org` 关联
- 安全执行：静态只读校验、参数绑定、SQLite 只读连接
- 可信度分级：A级自动执行，B/C级确认或复核，D级拒绝
- 证据链：指标口径、表、参数、SQL、校验结果和数据源
- SSE接口和单页演示界面
- 两阶段执行：先生成可编辑的业务查询计划，确认当前版本后才生成SQL
- 计划版本与哈希校验：计划修改后旧确认自动失效
- 多轮会话状态机：clarifying → awaiting_confirmation → confirmed → executing → completed
- SQLite持久化：会话、消息、QueryPlan版本和执行记录
- `/api/v1`统一响应、错误码和请求ID
- Alembic数据库迁移

生产 API 不会静默降级到关键词规则。缺少百炼凭证或模型调用失败时会明确停止，避免用户误以为系统仍在使用大模型分析。规则规划器仅用于离线单元测试。

## 百炼模型配置

配置与企业级 AI 智能体平台的 `dashscope-reasoning` 档案保持一致。开发环境直接编辑项目根目录 `.env`：

```dotenv
DASHSCOPE_API_KEY=填写百炼API-Key
SQLPILOT_BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SQLPILOT_BAILIAN_MODEL=qwen3.6-plus-2026-04-02
SQL_CANDIDATE_COUNT=3
```

`.env` 已加入 `.gitignore`，不会进入版本库。修改配置后需要重启 SQLPilot 服务。生产部署仍建议使用企业平台的挂载密钥或 Vault。

## 启动

本项目复用现有 `enterprise-ai` Conda 环境：

```powershell
conda run -n enterprise-ai python -m pip install -e ".[dev]"
conda run -n enterprise-ai uvicorn app.api:app --reload
```

浏览器打开 <http://127.0.0.1:8000>。

首次启动会初始化管理员账号。请通过环境变量`BOOTSTRAP_ADMIN_USERNAME`和`BOOTSTRAP_ADMIN_PASSWORD`配置一次性初始凭据，并在首次登录后立即修改密码。登录页为 <http://127.0.0.1:8000/login>，用户管理页为 <http://127.0.0.1:8000/admin/users>。

```text
AUTH_REQUIRED=true
SQLPILOT_SECRET_KEY=独立的高强度随机密钥
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=一次性初始强密码
```

正式环境先执行迁移，并关闭自动建表：

```powershell
conda run -n enterprise-ai alembic upgrade head
# .env: AUTO_CREATE_SCHEMA=false
conda run -n enterprise-ai uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 正式 API v1

```text
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
POST /api/v1/conversations
GET  /api/v1/conversations/{id}
POST /api/v1/conversations/{id}/messages
POST /api/v1/conversations/{id}/confirm
POST /api/v1/conversations/{id}/execute
```

每次用户补充都会生成不可变的 QueryPlan 新版本。模型发现歧义时会返回结构化澄清问题；未解决澄清、旧版本或哈希不一致时均拒绝确认和执行。

## 模块边界

```text
app/core             配置、统一错误
app/planning         QueryPlan v1、百炼适配器、Prompt、摘要与执行适配
app/conversation     会话聚合、状态机、持久化仓储与服务
app/infrastructure   SQLAlchemy异步数据库
app/api_v1           版本化HTTP接口
app/engine.py        受控SQL编译、校验与只读执行（待继续拆分）
```

## 运行核心测试

核心测试只依赖 Python 标准库：

```powershell
conda run -n enterprise-ai pytest -q
```

## API

```http
POST /api/query
Content-Type: application/json

{
  "question": "统计2025年各医院每月基金支付金额及环比",
  "confirmed": false
}
```

流式接口为 `POST /api/query/stream`，按节点发送 SSE 事件。

推荐的可信查询流程使用以下接口：

```text
POST  /api/plans                         生成业务查询计划（不生成SQL）
PATCH /api/plans/{session_id}            调整计划并生成新版本
POST  /api/plans/{session_id}/execute    确认当前版本后生成、校验并执行SQL
```

## 后续路线

1. 将 `app/planner.py` 替换为结构化 LLM Query Plan，同时保留认证指标闭集约束。
2. 将静态目录替换为 BGE-M3 稠密/稀疏检索与 RRF 融合。
3. 将静态 JOIN 关系替换为带粒度、基数、时效和可信度属性的 Neo4j 路径规划。
4. 引入 SQLGlot AST 字段级校验、EXPLAIN 成本控制和执行错误分类修复。
5. 增加人工认证查询、反馈案例库和可重复评测集。
