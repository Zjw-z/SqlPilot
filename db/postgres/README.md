# SQLPilot PostgreSQL 测试库

建议安装 PostgreSQL 17 或 18（Windows x64），同时安装 pgAdmin。数据库端口保持默认 `5432` 即可。

## 初始化

先在 pgAdmin 或 `psql` 中创建数据库：

```sql
CREATE DATABASE sqlpilot_test WITH ENCODING 'UTF8';
```

然后按顺序执行：

```powershell
psql -U postgres -d sqlpilot_test -f db/postgres/01_schema.sql
psql -U postgres -d sqlpilot_test -f db/postgres/02_seed.sql
psql -U postgres -d sqlpilot_test -f db/postgres/03_readonly_role.sql
```

最后以管理员身份创建应用连接账号，不要把真实密码提交到代码仓库：

```sql
CREATE USER sqlpilot_app WITH PASSWORD '替换为强密码';
GRANT sqlpilot_readonly TO sqlpilot_app;
ALTER ROLE sqlpilot_app SET statement_timeout = '15s';
ALTER ROLE sqlpilot_app SET default_transaction_read_only = on;
```

## 数据范围

- 6 家医疗机构，覆盖多个等级、类型和区县。
- 2025-01 至 2026-08 的结算数据。
- 每个机构每月包含住院、门诊、有效和撤销结算。
- 2026 年各月设置了不同同比增长幅度，便于验证“增长较高月份”。
- 结算主表和费用明细表是一对多关系，可测试多表 Join。
- 所有表和关键字段均有中文注释，后续可用于 Schema RAG。

`02_seed.sql` 会清空并重建测试数据，只能用于测试数据库。

## 医保结算清单规范数据集

根据《医疗保障基金结算清单采集接口规范 V2.3》生成的镜像测试结构：

```powershell
psql -U postgres -d sqlpilot_test -f db/postgres/04_nhsa_schema.sql
psql -U postgres -d sqlpilot_test -f db/postgres/05_nhsa_seed.sql
psql -U postgres -d sqlpilot_test -f db/postgres/06_nhsa_dictionary.sql
```

`04_nhsa_schema.sql` 包含规范中的 13 张业务表和完整字段注释。测试库保留接口字段名、类型和长度；仅对主键和核心关联键设置数据库非空约束，原规范的“接口必填”要求保存在字段注释中。这是为了支持分析和 Text-to-SQL 测试，不应作为生产接口报文校验库直接使用。

`05_nhsa_seed.sql` 生成 2025-01 至 2026-08 的全合成数据，不包含真实姓名、证件号码或患者信息。主要覆盖：

- 医疗机构、就诊、结算清单、结算、诊断、收费分类和基金支付；
- 住院与门诊、有效与撤销结算；
- 医疗费总额、基金支付总额和个人支付；
- 多机构月度同比增长差异。

`06_nhsa_dictionary.sql` 包含规范附录中的 1,420 条代码字典值，可用于枚举解释、字段值检索和 Schema RAG。

如规范文档更新，可重新生成结构：

```powershell
python tools/generate_nhsa_schema.py "规范文档.docx" db/postgres/04_nhsa_schema.sql --dictionary-output db/postgres/06_nhsa_dictionary.sql
```
