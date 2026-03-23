# Repo + Dependency Context MCP 产品开发文档（Codex 执行版）

版本：v1.0  
作者：OpenAI ChatGPT  
目标读者：Codex / 开发者 / 技术负责人  
文档用途：作为 **单仓库、单产品、可直接开工** 的详细开发规范。该文档默认目标是先完成 **MVP**，禁止偏离范围做“通用 AI 知识库平台”。

---

## 0. 一页版结论

### 产品一句话
构建一个 **Repo + Dependency Context MCP** 服务：在 Coding Agent 需要上下文时，返回“当前任务最小充分证据包”，而不是返回自由回答。

### 目标用户
- 使用 Codex / Claude Code / Cursor / Cline / 自建 agent 的程序员团队
- 需要基于 **私有代码仓库 + 官方依赖文档** 做开发、排错、升级、解释的人

### MVP 必须解决的 4 个问题
1. 用户问“某功能入口在哪”，系统能召回正确代码与相关文档。
2. 用户问“升级某依赖后这个问题怎么改”，系统能同时召回 **官方 migration guide** 和 **项目内封装代码**。
3. 用户问“这个报错最可能看哪些文件”，系统能召回代码、PR、issue、设计文档。
4. 系统不能跨租户、跨仓库、跨权限泄露内容。

### MVP 严格边界
做：
- repo code
- repo docs
- PR / issue / commit metadata
- dependency official docs / changelog / migration guide
- hybrid retrieval
- rerank
- ACL
- MCP server
- offline / online eval

不做：
- 自动改代码
- 通用聊天 UI
- Slack / Notion / Confluence 接入
- 自研向量数据库
- 多模型编排
- 复杂计费系统

### 交付顺序
1. 项目脚手架  
2. 数据模型与数据库  
3. repo ingest  
4. chunking + indexing  
5. hybrid retrieval  
6. dependency docs ingest  
7. rerank + evidence packing  
8. MCP tools  
9. eval harness  
10. playground + observability  
11. 安全部署

---

## 1. 产品定义

## 1.1 产品名称
Repo + Dependency Context MCP

## 1.2 产品定位
这是一个 **context compiler**，不是聊天机器人。  
职责是从多种 source of truth 中，选出 **最新、最权威、与当前任务最相关、且用户有权限看到** 的证据块，供上层大模型使用。

## 1.3 核心价值
- 降低 coding agent 幻觉
- 让 agent 使用私有仓库知识
- 让 agent 获取官方依赖的最新版变更信息
- 让检索结果具备版本感、权限感和证据可追溯性

## 1.4 典型使用场景
1. **Locate**
   - “支付成功后发邮件的入口在哪？”
2. **Explain**
   - “我们项目里的 AuthMiddleware 做了哪些额外校验？”
3. **Migration**
   - “升级 antd 6 后 Modal 的行为差异在哪里？”
4. **Debug**
   - “这个空指针异常最可能跟哪些文件、哪些变更相关？”
5. **Impact Analysis**
   - “改动 User model 会影响哪些 handler / service / docs？”

## 1.5 北极星指标
- `Evidence Success Rate`：查询后 top 5 证据中含有正确关键证据的比例
- `Grounded Answer Rate`：上层模型基于证据生成的答案中，关键结论均能被证据支持的比例
- `Freshness Win Rate`：新官方文档与旧内部笔记冲突时，新且权威的证据优先出现的比例
- `ACL Leakage = 0`

---

## 2. 产品范围与非目标

## 2.1 MVP 范围
### 输入源
- Git 仓库代码
- 仓库内 Markdown / ADR / 设计文档
- GitHub PR / issue / commit metadata
- 依赖官方文档（仅官方站点）
- 依赖 changelog / release notes / migration guides

### 输出能力
- 面向 MCP 的 4 个工具
- 面向内部调试的 REST API
- 可视化 playground（只给内部使用）
- 评测与日志系统

## 2.2 明确不做
- 不做自动代码修改与提交
- 不做多租户计费
- 不做复杂权限管理后台
- 不做跨应用大一统知识库
- 不做自然语言全文回答 API
- 不做 SaaS 商业化包装

---

## 3. 用户故事与验收标准

## 3.1 用户故事 A：定位功能入口
**作为** 开发者  
**我希望** 输入“订单支付成功后的邮件发送入口在哪”  
**以便** 快速找到核心文件和相关设计文档

### 验收标准
- top 5 中至少包含一个真实入口文件
- 若存在相关 ADR / README，应至少召回一份
- 返回结果应包含 `why_selected`

## 3.2 用户故事 B：依赖升级
**作为** 开发者  
**我希望** 输入“升级 antd 6 后 Form.Item 校验变化和我们项目封装差异”  
**以便** 同时看到官方迁移文档和项目内部封装

### 验收标准
- 返回至少一条官方 migration / changelog 证据
- 返回至少一条仓库内部 wrapper / adapter 证据
- 若版本不明确，系统应在响应中给出缺失信息提示

## 3.3 用户故事 C：排查报错
**作为** 开发者  
**我希望** 输入异常栈或症状描述  
**以便** 快速定位相关代码、近期改动和 runbook

### 验收标准
- top 5 中包含最相关代码块
- 若近期 PR 明显相关，应至少召回一条
- 返回应包含 `related_changes` 或可通过工具继续获取

## 3.4 用户故事 D：权限隔离
**作为** 企业用户  
**我希望** 系统只返回我有权限访问的内容  
**以便** 避免私有代码或机密文档泄露

### 验收标准
- 任一查询都不可返回未授权仓库内容
- 评测中跨租户召回错误为 0

---

## 4. 功能需求

## 4.1 必做功能列表
1. 仓库接入
2. 文档 ingest
3. 依赖解析
4. 依赖官方文档抓取
5. chunking
6. embedding + FTS 索引
7. hybrid retrieval
8. rerank
9. evidence packing
10. ACL 过滤
11. MCP server
12. REST API
13. query logging
14. offline eval
15. online feedback

## 4.2 可后置功能
- reranker 模型替换
- GitLab 接入
- Bitbucket 接入
- Slack / Notion / Confluence
- 图谱扩展为独立服务
- 企业 SSO

---

## 5. 非功能需求

## 5.1 性能
- P50 检索延迟 < 1.5s
- P95 检索延迟 < 3s
- 单次查询默认返回 5–8 个证据块
- ingest 单仓库 10k 文件在可接受时间内完成（优先稳定，不追求极限）

## 5.2 可用性
- ingest 作业可重试
- 索引过程幂等
- 查询失败时返回明确错误码与原因

## 5.3 安全性
- 严格 tenant_id / repo_id / acl_scope 过滤
- 所有查询日志脱敏保存
- 依赖官方文档抓取仅允许白名单域名

## 5.4 可观测性
- 每次查询记录：
  - query
  - task_type
  - candidates
  - final evidence
  - latency
  - filters applied
  - pack result
  - feedback
- 每次 ingest 记录：
  - source
  - item count
  - chunk count
  - duration
  - failures

---

## 6. 技术约束与默认实现

## 6.1 技术栈
- Python 3.11
- FastAPI
- PostgreSQL 15+
- pgvector
- Redis
- Celery（或 RQ；本规范默认 Celery）
- SQLAlchemy 2.x
- Alembic
- tree-sitter
- httpx
- pydantic v2
- pytest
- OpenTelemetry
- Docker Compose（开发环境）

## 6.2 为什么这样选
- 目标是快速完成 MVP，而不是自研搜索基础设施
- Postgres + pgvector + FTS 足以支撑 MVP
- tree-sitter 足以完成代码符号级切块
- FastAPI 同时适合 REST 与 MCP 封装

## 6.3 外部依赖（可替换）
- Embedding provider：可配置，先预留接口
- Rerank provider：可配置，先用简单规则或轻模型
- GitHub API：默认主接入方式

---

## 7. 领域模型

## 7.1 核心对象
- Tenant
- User
- Repo
- Source
- Document
- Chunk
- Symbol
- Dependency
- DependencyDoc
- IngestJob
- QueryLog
- QueryResult
- EvalDataset
- EvalCase
- EvalRun

## 7.2 关键概念解释
### Source
原始来源，例如：
- repo_code
- repo_doc
- pr
- issue
- commit
- vendor_doc

### Document
逻辑文档单位，例如：
- 一个源码文件
- 一个 Markdown 文件
- 一篇 PR 描述
- 一节 migration 文档页面

### Chunk
索引与检索的最小单元。  
要求：
- 具备元数据
- 具备 context_prefix
- 具备 text
- 具备 embedding 与 FTS 内容

### Symbol
代码级语义单元，例如：
- function
- class
- method
- interface
- route handler

---

## 8. 数据库设计

## 8.1 表设计概览
建议至少创建以下表：

1. `tenants`
2. `users`
3. `repos`
4. `repo_memberships`
5. `sources`
6. `documents`
7. `chunks`
8. `symbols`
9. `dependencies`
10. `dependency_docs`
11. `ingest_jobs`
12. `query_logs`
13. `query_results`
14. `eval_datasets`
15. `eval_cases`
16. `eval_runs`
17. `eval_case_results`

## 8.2 关键表字段建议

### `repos`
```sql
id uuid pk
tenant_id uuid not null
name text not null
provider text not null
external_id text not null
default_branch text not null
is_active boolean not null default true
created_at timestamptz not null
updated_at timestamptz not null
```

### `sources`
```sql
id uuid pk
tenant_id uuid not null
repo_id uuid null
source_type text not null
authority text not null
path_or_url text not null
external_ref text null
version_range text null
commit_sha text null
doc_version text null
updated_at_source timestamptz null
acl_scope jsonb not null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

### `documents`
```sql
id uuid pk
tenant_id uuid not null
repo_id uuid null
source_id uuid not null
title text null
section_title text null
mime_type text not null
language text null
checksum text not null
raw_text text not null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

### `chunks`
```sql
id uuid pk
tenant_id uuid not null
repo_id uuid null
document_id uuid not null
source_id uuid not null
chunk_index int not null
chunk_type text not null
symbol_path text null
text text not null
context_prefix text not null
token_count int not null
embedding vector(...)
fts tsvector
authority text not null
version_range text null
updated_at_source timestamptz null
acl_scope jsonb not null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

### `symbols`
```sql
id uuid pk
tenant_id uuid not null
repo_id uuid not null
document_id uuid not null
symbol_name text not null
symbol_kind text not null
symbol_path text not null
parent_symbol_path text null
start_line int not null
end_line int not null
signature text null
created_at timestamptz not null
updated_at timestamptz not null
```

### `dependencies`
```sql
id uuid pk
tenant_id uuid not null
repo_id uuid not null
package_name text not null
ecosystem text not null
declared_version text not null
resolved_version text null
manager text not null
created_at timestamptz not null
updated_at timestamptz not null
```

### `dependency_docs`
```sql
id uuid pk
package_name text not null
ecosystem text not null
doc_type text not null
authority text not null
url text not null
version_range text null
title text not null
section_title text null
raw_text text not null
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

### `query_logs`
```sql
id uuid pk
tenant_id uuid not null
repo_id uuid null
user_id uuid null
query_text text not null
task_type text null
normalized_query text null
filters jsonb not null default '{}'
latency_ms int null
result_count int not null default 0
clarify_needed boolean not null default false
metadata jsonb not null default '{}'
created_at timestamptz not null
```

### `query_results`
```sql
id uuid pk
query_log_id uuid not null
rank int not null
chunk_id uuid null
score_total double precision not null
score_lexical double precision null
score_dense double precision null
score_graph double precision null
score_freshness double precision null
score_authority double precision null
score_version_match double precision null
why_selected text not null
created_at timestamptz not null
```

## 8.3 必要索引
- `repos(tenant_id, external_id)`
- `sources(tenant_id, repo_id, source_type)`
- `documents(source_id, checksum)`
- `chunks(document_id, chunk_index)`
- `chunks USING GIN(fts)`
- `chunks USING ivfflat (embedding vector_cosine_ops)` 或等价向量索引
- `chunks(tenant_id, repo_id, authority)`
- `symbols(repo_id, symbol_path)`
- `dependencies(repo_id, package_name)`
- `query_logs(tenant_id, created_at desc)`

## 8.4 约束
- `checksum` 去重
- `chunk_index` 在 `document_id` 内唯一
- `rank` 在 `query_log_id` 内唯一

---

## 9. 仓库目录结构（建议）

```text
repo-context-mcp/
  app/
    api/
      routes/
      deps.py
      schemas/
    core/
      config.py
      logging.py
      security.py
      db.py
    models/
    services/
      ingest/
      parse/
      index/
      retrieve/
      rerank/
      pack/
      acl/
      eval/
      mcp/
    workers/
    prompts/
    utils/
  migrations/
  scripts/
  tests/
    unit/
    integration/
    e2e/
    fixtures/
  docs/
    architecture.md
    api.md
    eval.md
  docker/
  docker-compose.yml
  pyproject.toml
  Makefile
  README.md
```

---

## 10. 系统架构

## 10.1 组件划分
1. **API Server**
   - REST API
   - MCP endpoint
2. **Ingest Worker**
   - 拉取 repo / docs / PR / issue / dependency docs
3. **Parser**
   - 代码切块
   - Markdown 切块
   - PR/issue 切块
4. **Indexer**
   - 生成 context_prefix
   - embedding
   - FTS
5. **Retriever**
   - lexical / dense / graph candidates
6. **Reranker**
   - 规则打分或模型重排
7. **Packager**
   - 组装 evidence 输出
8. **Eval Runner**
   - 跑离线评测
9. **Playground**
   - 内部调试界面

## 10.2 逻辑流程
### ingest 流程
`repo connected -> fetch raw content -> normalize -> parse -> document -> chunk -> enrich metadata -> embed -> index`

### query 流程
`user query -> normalize -> classify -> candidate generation -> hard filter -> rerank -> pack -> log -> return`

---

## 11. 输入源接入规范

## 11.1 GitHub Repo 接入
### 输入方式
- GitHub App 安装
- 或本地 CLI：
```bash
ctx ingest ./repo
```

### MVP 接入内容
- 文件树
- 默认分支代码
- Markdown 文档
- PR 标题/正文/关键信息
- Issue 标题/正文
- Commit message

### 暂不做
- code review comments 深度解析
- 多分支全量索引
- PR diff 智能摘要

## 11.2 依赖接入
### 支持识别
- Node.js: `package.json`, lockfile
- Python: `requirements.txt`, `pyproject.toml`, lockfile
- Go: `go.mod`

### 输出
- package_name
- ecosystem
- declared_version
- resolved_version
- manager

## 11.3 依赖文档抓取规范
只允许抓取官方文档域名白名单。  
每个依赖至少尝试获取：
- docs
- changelog
- release notes
- migration guide

### 白名单策略
以 package -> domains 的映射文件实现，例如：
```yaml
antd:
  - ant.design
react:
  - react.dev
fastapi:
  - fastapi.tiangolo.com
```

### 注意
- 不抓社区博客
- 不抓问答站
- 不抓镜像站
- 若无法识别官方域名，则跳过并记录

---

## 12. 解析与切块规范

## 12.1 代码切块
### 原则
- 优先按 symbol 切
- 其次按逻辑段落切
- 过大 symbol 再二次切块
- 保留文件路径、symbol_path、行号范围

### 代码 chunk 元数据
- repo_id
- file_path
- language
- symbol_name
- symbol_kind
- symbol_path
- start_line
- end_line
- last_commit_sha
- last_updated_at

## 12.2 文档切块
### Markdown
- 按 heading 层级切
- 保留 title / heading path

### PR / Issue
- 标题
- 正文
- 关键字段（status、labels、author、merged_at）

### Migration / Changelog
- 按版本号与小节切
- 版本号必须进入 metadata

## 12.3 context_prefix 生成规范
每个 chunk 必须生成可供检索增强的上下文前缀。

### 代码示例
```text
Repo: shop-api
File: src/auth/middleware.ts
Symbol: requireAdmin
Kind: function
LastChanged: 2026-03-01
This chunk contains authorization logic for admin-only routes.
```

### 文档示例
```text
Package: antd
DocType: migration_guide
VersionRange: 6.x
Section: Form.Item validation behavior
This section explains breaking changes in validation behavior after upgrade.
```

---

## 13. 检索与重排设计

## 13.1 查询分类
支持以下 task_type：
- `locate`
- `explain`
- `migration`
- `debug`
- `impact_analysis`

若用户未显式传入，由内部分类器判断。

## 13.2 查询标准化
标准化步骤：
1. trim
2. lowercase（英文部分）
3. 删除无意义空白
4. 提取 package 名
5. 提取错误码 / 异常名
6. 提取 symbol / file hints
7. 提取 version hints

输出：
```json
{
  "normalized_query": "...",
  "entities": {
    "packages": ["antd"],
    "symbols": ["Form.Item"],
    "errors": [],
    "versions": ["6"]
  }
}
```

## 13.3 Candidate Generation
### lexical
- Postgres FTS top 30

### dense
- embedding similarity top 30

### graph expansion
来自以下关系：
- 同文件
- 同 symbol 父子关系
- 同 package 依赖文档
- 关联 PR / issue / commit

默认 top 10 补充。

## 13.4 Hard Filters
必须在 rerank 前执行：
- tenant filter
- repo filter
- ACL filter
- source_type filter（如果指定）
- version compatibility
- branch / default branch rule

## 13.5 打分策略（MVP）
总分建议：
```text
total_score =
  0.30 * lexical_score +
  0.30 * dense_score +
  0.15 * graph_score +
  0.10 * freshness_score +
  0.10 * authority_score +
  0.05 * version_match_score
```

### authority_score 规则建议
- official = 1.0
- internal_primary = 0.9
- internal_secondary = 0.7
- community = 0.3

### freshness_score 建议
按 source 更新时间做衰减，但只在同类候选中影响排序，避免最新但无关的内容抢占结果。

### version_match_score 建议
- 完全匹配 = 1.0
- 主版本匹配 = 0.8
- 近邻版本 = 0.5
- 不匹配 = 0

## 13.6 Clarify Gate
若满足任一条件，返回 `clarify_needed=true`：
- top1 与 top2 分差小于阈值
- 查询缺 package/version 且 task_type=migration
- 查询明显指向多个仓库组件
- 系统判断证据不足

### Clarify 输出格式
```json
{
  "clarify_needed": true,
  "questions": [
    "你当前升级的 antd 主版本是 5 到 6，还是 4 到 5？",
    "你指的是项目内封装的 ModalWrapper 还是直接使用的 antd Modal？"
  ]
}
```

## 13.7 Evidence Packing
返回 top 5–8 个证据块，每个包含：
- source_type
- title
- path_or_url
- symbol_path
- start_line / end_line
- snippet
- why_selected
- freshness_reason
- authority
- version_range

若存在冲突，还要返回：
- `conflicts`
- `gaps`

### 目标响应结构
```json
{
  "task_type": "migration",
  "clarify_needed": false,
  "evidence": [
    {
      "source_type": "vendor_doc",
      "title": "Ant Design v6 migration guide",
      "path_or_url": "https://...",
      "symbol_path": null,
      "snippet": "...",
      "why_selected": "Mentions Form.Item validation change",
      "freshness_reason": "Official guide for target major version",
      "authority": "official",
      "version_range": "6.x"
    }
  ],
  "conflicts": [],
  "gaps": []
}
```

---

## 14. MCP 设计

## 14.1 仅暴露 4 个工具
1. `search_context`
2. `get_source`
3. `get_related_changes`
4. `get_dependency_notes`

## 14.2 Tool: `search_context`
### 输入
```json
{
  "query": "升级 antd 6 后 Form.Item 校验变化",
  "repo": "shop-web",
  "branch": "main",
  "task_type": "migration",
  "top_k": 5
}
```

### 输出
返回 evidence 包。

### 约束
- `top_k` 默认 5，最大 8
- 不返回原始全文
- 必须遵守 ACL

## 14.3 Tool: `get_source`
### 输入
```json
{
  "path_or_url": "src/ui/ModalWrapper.tsx",
  "start_line": 1,
  "end_line": 120
}
```

### 输出
- 精确源码或文档片段
- 基本元数据

## 14.4 Tool: `get_related_changes`
### 输入
```json
{
  "path_or_symbol": "src/auth/middleware.ts:requireAdmin",
  "since_days": 90
}
```

### 输出
- 相关 PR
- commit
- issue 摘要

## 14.5 Tool: `get_dependency_notes`
### 输入
```json
{
  "package_name": "antd",
  "version_range": "6.x",
  "topic": "Form.Item validation"
}
```

### 输出
- 官方文档片段
- changelog 片段
- migration 指南片段

---

## 15. REST API 设计（内部调试用）

## 15.1 基础接口
- `POST /api/repos/connect`
- `POST /api/repos/{repo_id}/ingest`
- `GET /api/ingest-jobs/{job_id}`
- `POST /api/query/search`
- `GET /api/source`
- `GET /api/query/{query_id}`
- `POST /api/eval/run`
- `GET /api/eval/runs/{run_id}`

## 15.2 示例：`POST /api/query/search`
请求：
```json
{
  "tenant_id": "tenant_1",
  "repo_id": "repo_1",
  "query": "支付成功后发邮件的入口在哪",
  "task_type": "locate"
}
```

响应：
```json
{
  "query_id": "q_123",
  "task_type": "locate",
  "clarify_needed": false,
  "evidence": [],
  "conflicts": [],
  "gaps": [],
  "latency_ms": 820
}
```

---

## 16. 评测系统设计

## 16.1 评测目标
验证系统是否能：
- 找对证据
- 证据排得够前
- 选对新旧版本
- 选对权威来源
- 正确触发澄清
- 不泄露权限

## 16.2 数据集结构
每个 eval case 至少包含：
```yaml
id: migration_001
query: 升级 antd 6 后 Form.Item 校验变化
task_type: migration
tenant_id: tenant_1
repo_id: repo_shop_web
must_hit_sources:
  - vendor_doc:antd_v6_migration_form_item
  - repo_code:src/ui/form/FormItemWrapper.tsx
acceptable_sources:
  - repo_doc:docs/frontend/forms.md
must_not_hit_sources:
  - vendor_doc:antd_v4_legacy_notes
freshness_rule:
  prefer:
    - vendor_doc:antd_v6_migration_form_item
requires_clarification: false
```

## 16.3 离线指标
1. Recall@5
2. Recall@10
3. MRR
4. nDCG@5
5. Freshness Win Rate
6. Authority Win Rate
7. Clarification Precision
8. ACL Leakage
9. Grounded Answer Rate（可选二阶段）

## 16.4 上线门槛
- Recall@10 >= 0.90
- Freshness Win Rate >= 0.95
- Authority Win Rate >= 0.95
- Clarification Precision >= 0.80
- ACL Leakage = 0
- P95 latency < 3s

## 16.5 在线反馈
前端只提供 5 个反馈：
- 对
- 漏文档
- 文档过时
- 引错源
- 权限有问题

每周动作：
- 将失败案例回灌到 `eval_cases`

---

## 17. 测试计划

## 17.1 单元测试
覆盖：
- query normalization
- task classification
- chunking
- context_prefix generation
- scoring function
- ACL filters
- version matching

## 17.2 集成测试
覆盖：
- GitHub ingest -> parse -> index
- dependency doc ingest -> index
- search_context end-to-end
- MCP tool invocation

## 17.3 E2E 测试
构造一个 demo repo：
- 代码
- docs
- PR / issue
- 一个依赖（例如 antd）

验证：
- locate
- explain
- migration
- debug

## 17.4 安全测试
- 跨 tenant 查询
- repo 级 ACL
- 非白名单域名依赖抓取
- query log 脱敏

---

## 18. 监控与日志

## 18.1 指标
- query_count
- query_latency_ms
- ingest_job_duration_ms
- chunk_count
- index_failures
- clarify_rate
- freshness_override_rate
- acl_block_count
- dependency_doc_fetch_failures

## 18.2 日志字段
- request_id
- tenant_id
- repo_id
- user_id
- task_type
- filters
- candidate_count
- top_k
- elapsed_ms
- error_type

## 18.3 告警
- ingest 连续失败
- dependency 文档抓取异常升高
- P95 latency 超阈值
- ACL block 异常升高

---

## 19. 部署方案

## 19.1 本地开发
使用 Docker Compose 启动：
- api
- worker
- postgres
- redis

## 19.2 生产环境
可拆成：
- api deployment
- worker deployment
- postgres
- redis
- object storage
- optional ingress / gateway

## 19.3 环境变量
建议：
```env
APP_ENV=dev
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-large
RERANK_PROVIDER=internal
GITHUB_APP_ID=...
GITHUB_PRIVATE_KEY=...
ALLOWED_VENDOR_DOC_CONFIG=./config/vendor_domains.yaml
DEFAULT_TOP_K=5
MAX_TOP_K=8
```

---

## 20. 安全与权限设计

## 20.1 ACL 原则
- 所有 source / document / chunk 都带 `tenant_id`
- repo 私有内容只能在对应 repo 上下文内检索
- 所有查询必须带 tenant 和 repo 边界
- dependency docs 属于公共只读数据，但与 repo 查询组合时仍需 tenant 级日志隔离

## 20.2 白名单抓取
- 只抓官方域名
- 禁止任意 URL 抓取
- 抓取失败只记日志，不使用替代社区源

## 20.3 日志脱敏
对 query 中可能出现的 token、secret、access key 做脱敏。

---

## 21. 里程碑拆解

## 21.1 里程碑总览

### Milestone 0：脚手架与基础设施
交付物：
- 项目目录
- Docker Compose
- FastAPI 空服务
- Postgres / Redis 接通
- 基础 CI

### Milestone 1：领域模型与数据库
交付物：
- SQLAlchemy models
- Alembic 初始迁移
- 基本 CRUD
- ACL 核心字段落库

### Milestone 2：Repo Ingest
交付物：
- GitHub / CLI ingest
- documents / chunks 生成
- code / markdown / pr / issue parser

### Milestone 3：检索 MVP
交付物：
- FTS
- embedding
- hybrid retrieval
- basic scoring
- search API

### Milestone 4：Dependency Docs
交付物：
- dependency parser
- vendor doc fetcher
- vendor doc chunking
- version metadata

### Milestone 5：Evidence Packing + MCP
交付物：
- why_selected
- freshness_reason
- conflicts / gaps
- 4 个 MCP tools

### Milestone 6：Eval Harness
交付物：
- eval dataset format
- eval runner
- offline metrics
- report output

### Milestone 7：Playground + Observability
交付物：
- 简易内部 UI
- query inspect
- ingest inspect
- metrics + tracing

---

## 22. 任务拆解（可直接给 Codex）

以下任务默认按顺序执行。每个任务完成后必须通过对应验收标准。

## 22.1 Phase 0：初始化

### T-000 初始化仓库脚手架
**目标**：创建 Python 项目骨架  
**输入**：无  
**输出**：
- `app/`
- `tests/`
- `docker-compose.yml`
- `pyproject.toml`
- `Makefile`
- `README.md`

**完成定义**
- `make dev` 可启动空服务
- `GET /healthz` 返回 200

### T-001 配置系统与环境变量
**目标**：建立统一配置入口  
**输出**
- `app/core/config.py`
- `.env.example`

**完成定义**
- 本地能读取数据库、Redis、provider 等配置
- 配置缺失时报错明确

### T-002 日志与 tracing 基础
**目标**：统一 request_id 与结构化日志  
**输出**
- JSON logging
- request_id middleware

**完成定义**
- 每个请求日志都带 request_id

---

## 22.2 Phase 1：数据库与模型

### T-010 建立核心 ORM 模型
**目标**：实现 tenants / repos / sources / documents / chunks / symbols / dependencies / query_logs  
**完成定义**
- 所有模型有主键、时间字段、必要外键
- 能通过 Alembic 生成初始迁移

### T-011 建立 Alembic 初始迁移
**完成定义**
- 本地迁移成功
- 表与索引创建成功

### T-012 建立 Repository 层
**目标**：封装常用 DB 访问
**完成定义**
- 可创建 repo
- 可保存 documents/chunks
- 可记录 query_logs / query_results

---

## 22.3 Phase 2：Repo Ingest

### T-020 CLI ingest 命令
**目标**：支持本地仓库导入  
**命令**
```bash
ctx ingest ./demo_repo --repo-name demo
```

**完成定义**
- 能遍历文件
- 能写入 repo/document/source 记录

### T-021 GitHub ingest service
**目标**：支持通过 GitHub 拉取默认分支内容  
**完成定义**
- 能拉取文件树
- 能保存原始内容

### T-022 代码 parser
**目标**：使用 tree-sitter 解析 symbol  
**完成定义**
- 支持至少 2 种语言（建议 TypeScript、Python）
- 生成 symbol_path 与行号信息

### T-023 Markdown parser
**目标**：按 heading 切块  
**完成定义**
- 生成 section_title
- heading path 写入 metadata

### T-024 PR / issue / commit parser
**目标**：将 PR、issue、commit message 转成 document/chunk  
**完成定义**
- 支持 title / body / metadata
- merged_at / labels / author 写入 metadata

### T-025 context_prefix builder
**目标**：为每个 chunk 生成 prefix  
**完成定义**
- 代码 / 文档 / vendor doc 三类模板可用
- prefix 与正文分开存储

### T-026 checksum / 幂等写入
**目标**：重复 ingest 不产生重复记录  
**完成定义**
- checksum 相同则跳过或更新
- ingest 可重试

---

## 22.4 Phase 3：索引与检索

### T-030 FTS 索引
**目标**：建立 Postgres FTS  
**完成定义**
- chunks 可被关键词检索
- 中文与英文基本可搜索（允许先用简单实现）

### T-031 Embedding pipeline
**目标**：为 chunks 生成向量  
**完成定义**
- 支持批量 embedding
- 嵌入结果保存到 chunks.embedding

### T-032 lexical retrieval
**目标**：返回 FTS top N 候选  
**完成定义**
- 支持 tenant / repo / source_type 过滤

### T-033 dense retrieval
**目标**：返回向量 top N 候选  
**完成定义**
- 支持 tenant / repo 过滤

### T-034 graph expansion
**目标**：基于同文件、symbol、相关变更补充候选  
**完成定义**
- 输入一个候选列表，可补充相关 chunk

### T-035 query normalization
**目标**：提取 package / version / symbol / error hints  
**完成定义**
- 单元测试覆盖典型 query

### T-036 task classification
**目标**：判断 locate / explain / migration / debug / impact_analysis  
**完成定义**
- 提供函数接口和测试

### T-037 hard filter 层
**目标**：统一 ACL / version / source 过滤  
**完成定义**
- 所有候选经过统一过滤
- 未授权候选不会进入 rerank

### T-038 scoring + rerank
**目标**：实现 MVP 规则打分  
**完成定义**
- 返回各子分数
- 返回 total_score
- 可配置权重

### T-039 evidence packer
**目标**：输出标准 evidence 结构  
**完成定义**
- 包含 why_selected / freshness_reason / conflicts / gaps
- 默认返回 5 个证据

### T-040 search API
**目标**：开放 `POST /api/query/search`  
**完成定义**
- 端到端可查询
- 有 query_logs 和 query_results 记录

---

## 22.5 Phase 4：Dependency Docs

### T-050 dependency parser
**目标**：解析 package.json / requirements / go.mod  
**完成定义**
- 至少支持 Node 与 Python
- 提取 package + version

### T-051 vendor domain config
**目标**：维护 package -> 官方域名映射  
**完成定义**
- YAML 配置可读取
- 不在白名单的依赖跳过

### T-052 vendor doc fetcher
**目标**：抓取官方 docs / changelog / migration  
**完成定义**
- 保存原始文本与 metadata
- 标记 authority=official

### T-053 vendor doc parser
**目标**：按版本与 section 切块  
**完成定义**
- version_range 落入 metadata
- 文档 chunk 可检索

### T-054 repo dependency link
**目标**：把 repo 中声明的依赖与 vendor docs 关联  
**完成定义**
- migration 查询时可优先命中对应依赖文档

---

## 22.6 Phase 5：MCP 与源码读取

### T-060 `get_source` 实现
**目标**：按 path/line 返回内容片段  
**完成定义**
- 支持 repo code 和 vendor docs

### T-061 `get_related_changes` 实现
**目标**：查相关 PR / issue / commit  
**完成定义**
- 默认 90 天窗口
- 返回结构化摘要

### T-062 `get_dependency_notes` 实现
**目标**：按 package + topic 返回官方文档片段  
**完成定义**
- 能按 version_range 过滤

### T-063 `search_context` MCP 封装
**目标**：将 search API 封装为 MCP 工具  
**完成定义**
- 4 个工具都能通过 MCP 调用
- JSON schema 明确

### T-064 MCP 鉴权
**目标**：MCP 调用时可识别 tenant / repo / user 上下文  
**完成定义**
- 未提供必要上下文时报错明确

---

## 22.7 Phase 6：评测

### T-070 eval dataset schema
**目标**：定义 YAML / JSONL 格式  
**完成定义**
- 支持 must_hit / must_not_hit / freshness_rule / requires_clarification

### T-071 eval case loader
**目标**：读取数据集并转成内部对象  
**完成定义**
- 可批量加载

### T-072 retrieval metrics
**目标**：实现 Recall@K / MRR / nDCG  
**完成定义**
- 对每次 eval case 产出结果

### T-073 freshness / authority / ACL 指标
**目标**：实现业务关键指标  
**完成定义**
- 可输出总报告

### T-074 eval runner CLI
**命令**
```bash
ctx eval run ./evals/demo.yaml
```

**完成定义**
- 输出 markdown 或 json 报告

### T-075 baseline runner
**目标**：支持 baseline 对比  
**完成定义**
- 至少支持 lexical only
- dense only
- hybrid
- hybrid+rereank

---

## 22.8 Phase 7：内部工具与观测

### T-080 playground
**目标**：最小内部查询界面  
**功能**
- 输入 query
- 查看 evidence
- 查看分数与 why_selected

### T-081 ingest job inspect
**目标**：查看 ingest 作业状态  
**完成定义**
- 能看到成功/失败、数量、错误原因

### T-082 metrics + tracing
**目标**：接入 OpenTelemetry 与基本指标  
**完成定义**
- query 流程可追踪
- ingest 流程可追踪

### T-083 feedback ingest
**目标**：记录“对/漏文档/过时/引错源/权限有问题”  
**完成定义**
- 可关联 query_id
- 可后续导出做 eval 增量

---

## 23. 每个阶段的验收清单

## 23.1 阶段验收：Repo Ingest
- [ ] 能导入本地 demo repo
- [ ] 代码文件生成 chunks
- [ ] Markdown 生成 chunks
- [ ] 至少支持两种语言 symbol 抽取
- [ ] 重复导入不重复写入

## 23.2 阶段验收：检索
- [ ] 给定 locate query，返回相关代码块
- [ ] 给定 explain query，返回代码 + 文档
- [ ] 候选在 ACL 内
- [ ] query logs / results 落库

## 23.3 阶段验收：依赖文档
- [ ] 依赖版本可被解析
- [ ] 官方 migration 文档可索引
- [ ] migration 查询可召回 vendor docs

## 23.4 阶段验收：MCP
- [ ] 4 个工具可调
- [ ] 工具 schema 明确
- [ ] 所有工具受 ACL 约束

## 23.5 阶段验收：评测
- [ ] eval runner 可运行
- [ ] 输出 Recall@5/10、MRR、nDCG
- [ ] 输出 Freshness / Authority / ACL 指标

---

## 24. Baseline 与对比实验要求

在任何“效果提升”宣称前，必须与以下 baseline 对比：
1. lexical only
2. dense only
3. lexical + dense
4. lexical + dense + rerank
5. lexical + dense + rerank + vendor doc version filter

对比项：
- Recall@5
- Recall@10
- MRR
- Freshness Win Rate
- Clarification Precision
- Latency

---

## 25. Demo 数据集要求

为了让 Codex 能立即开发和自测，仓库内需要包含一套最小 demo fixtures：

```text
tests/fixtures/demo_repo/
  src/
  docs/
  .github/mock_prs.json
  .github/mock_issues.json
tests/fixtures/vendor_docs/
  antd/
    migration_v6.md
    changelog_v6.md
```

### Demo case 至少包含
1. locate case
2. explain case
3. migration case
4. debug case
5. ambiguity case
6. stale doc conflict case
7. ACL isolation case

---

## 26. Codex 执行约束

这是给 Codex 的硬性约束，防止过度设计：

1. 只实现 MVP，不扩需求。
2. 优先保证 ingest -> retrieve -> pack -> eval 闭环。
3. 任何需要额外 UI 的功能都延后。
4. 除非文档明确要求，否则不要引入新的基础设施。
5. 所有外部 provider 都要通过抽象接口封装。
6. 所有核心逻辑必须可单元测试。
7. 所有搜索结果都必须带证据与元数据。
8. 所有查询都必须记录日志。
9. 所有跨 repo / 跨 tenant 内容默认禁止。
10. 所有 vendor docs 必须通过白名单校验。

---

## 27. 建议的开发顺序（最短路径）

### 第 1 周目标
- 完成脚手架
- 完成数据库
- 完成本地 repo ingest
- 完成代码 / Markdown chunking

### 第 2 周目标
- 完成 FTS + embedding
- 完成 search API
- 完成 basic packer
- 跑通 locate / explain case

### 第 3 周目标
- 完成 dependency 解析
- 完成 vendor doc ingest
- 跑通 migration case
- 完成 MCP tools

### 第 4 周目标
- 完成 eval runner
- 完成 baseline 对比
- 完成 playground
- 完成观测和安全检查

> 说明：上面的“周”只是逻辑分组，不代表必须按自然周执行；Codex 执行时以 Milestone 完成为准。

---

## 28. 第一版完成定义（Release Criteria）

满足以下条件才算 MVP 完成：
- [ ] demo repo 全部 ingest 成功
- [ ] 4 个 MCP 工具全部可用
- [ ] 至少支持 TypeScript 和 Python repo
- [ ] 能识别 Node 与 Python 依赖
- [ ] migration case 能召回官方文档
- [ ] offline eval 可运行并输出报告
- [ ] Recall@10 >= 0.90（demo 集）
- [ ] ACL Leakage = 0
- [ ] P95 latency < 3s（demo / 小规模环境）

---

## 29. Appendix A：伪代码

## 29.1 Query Pipeline
```python
def search_context(query, tenant_id, repo_id, task_type=None, top_k=5):
    normalized = normalize_query(query)
    inferred_task = task_type or classify_task(normalized)

    lexical = lexical_search(normalized, tenant_id=tenant_id, repo_id=repo_id, limit=30)
    dense = dense_search(normalized, tenant_id=tenant_id, repo_id=repo_id, limit=30)
    graph = graph_expand(lexical + dense, repo_id=repo_id, limit=10)

    candidates = dedupe(lexical + dense + graph)
    candidates = apply_hard_filters(
        candidates,
        tenant_id=tenant_id,
        repo_id=repo_id,
        task_type=inferred_task,
        entities=normalized.entities,
    )

    scored = rerank(candidates, normalized, inferred_task)
    clarify = maybe_clarify(scored, normalized, inferred_task)
    if clarify:
        return clarify_response(clarify)

    packed = pack_evidence(scored[:top_k], normalized, inferred_task)
    log_query(query, normalized, inferred_task, packed)
    return packed
```

## 29.2 Rerank
```python
def score(candidate, query):
    return (
        0.30 * candidate.lexical_score +
        0.30 * candidate.dense_score +
        0.15 * candidate.graph_score +
        0.10 * freshness_score(candidate, query) +
        0.10 * authority_score(candidate) +
        0.05 * version_match_score(candidate, query)
    )
```

---

## 30. Appendix B：示例 Eval Case

```yaml
id: debug_001
query: 用户登录时偶发 500，栈里出现 NullPointer on profile mapper
task_type: debug
tenant_id: tenant_demo
repo_id: repo_shop_api
must_hit_sources:
  - repo_code:src/profile/ProfileMapper.ts
  - pr:pr_182_fix_profile_mapper_null
acceptable_sources:
  - repo_doc:docs/user-profile.md
must_not_hit_sources:
  - repo_code:src/payment/*
requires_clarification: false
```

---

## 31. Appendix C：建议给 Codex 的执行顺序 Prompt

将下面这段作为你给 Codex 的第一条系统/任务提示：

```text
你正在实现一个名为 Repo + Dependency Context MCP 的 MVP 产品。
目标是构建一个 context compiler，而不是聊天机器人。

请严格按以下顺序实现，不要自行扩需求：
1. 项目脚手架
2. 数据库模型与迁移
3. 本地 repo ingest
4. 代码与 Markdown chunking
5. FTS + embedding + hybrid retrieval
6. evidence packer
7. dependency parser 与 vendor docs ingest
8. 4 个 MCP tools
9. eval runner
10. playground 与 observability

硬性要求：
- Python 3.11 + FastAPI + Postgres + pgvector + Redis + Celery
- 支持 TypeScript 与 Python 代码解析
- 所有查询结果必须带 evidence、why_selected、authority、freshness_reason
- 所有查询必须落日志
- 严格 tenant / repo / ACL 隔离
- 只抓官方依赖文档白名单域名
- 每完成一个任务都补齐测试
- 优先可运行，再优化

请先输出：
A. 仓库目录结构
B. 依赖清单
C. 第一阶段要创建的文件列表
D. 第一阶段的代码骨架
```

---

## 32. 最后说明

这份文档是 **以“让 Codex 能顺着文档逐步实现”为第一原则** 写的。  
如果要继续扩展，建议下一份文档只做两件事之一：

1. 写成更严格的 `openapi.yaml + MCP tool schema + SQL migrations`
2. 写成 `issues backlog / sprint board`，拆成更细的任务卡片

在当前阶段，不要再扩功能边界，先把闭环做出来。

---

## 33. 当前实现状态校准（2026-03-23）

下面这部分用于说明：当前代码主线已经超过本 PRD 最初定义的 MVP 截止线。

### 33.1 已完成且稳定落地的能力
- repo code / repo docs ingest
- PR / issue / commit metadata ingest
- dependency parser + official vendor docs whitelist ingest
- hybrid retrieval + rerank + evidence packing
- 4 个 MCP tools
- offline eval runner
- internal playground + observability
- CLI / task / API 三条 eval 执行入口

### 33.2 已超出最初 MVP 的扩展项
- durable sync state：
  - `sync_runs`
  - `sync_cursors`
- retrieval experimentation：
  - candidate profiles
  - rerank profiles
  - dual-route candidate generation
- eval experimentation：
  - baseline comparison
  - profile matrix execution
  - per-case diagnostics
  - latest / baseline / matrix comparison views
- CLI experiment output modes：
  - `--json-only`
  - `--table-only`
  - `--best-only`
  - `--failures-only`

### 33.3 与 PRD 仍有差距的项
- `feedback ingest` 仍未落地
- `related changes` 仍是增强版 MVP 匹配，不是完整 change graph
- dependency docs 仍是 bounded discovery / sync，不是 crawler-level 全站抓取
- 生产级 OpenTelemetry / tracing 仍偏轻量实现
- 文档中列出的部分上线指标尚未被系统化 gate：
  - `Recall@10 >= 0.90`
  - `P95 latency < 3s`

### 33.4 当前阶段建议重新命名
当前项目状态更适合归类为：

`Phase 4: Retrieval Experimentation and Eval-Driven Tuning`

也就是说，当前工作的主要目标已经不是“把 MVP 主链做出来”，而是：
- 通过 eval/baseline/matrix 闭环持续比较检索策略
- 让 retrieval profile 的实验结果可记录、可比较、可解释

### 33.5 下一阶段边界建议
如果继续沿当前路线推进，建议优先做：

1. `related changes` 深化
- file / symbol / PR / issue / commit 的图式关联
- 减少当前基于规则匹配的脆弱性
 - 当前已完成：
   - repo-backed query expansion
   - canonical file/symbol refs during change ingest
   - `match_kind` / `match_evidence` result explanation

2. dependency docs 深化
- 更强的增量同步策略
- 更好的 release notes / migration sections 结构化抽取
 - 当前已完成：
   - heading / version heading extraction
   - `section_title` and `structure_kind` persistence
   - snapshot-based vendor-doc sync cursor
   - candidate-set and content-hash checkpointing

3. eval dataset 深化
- 增加 explain / debug / ambiguity / stale-doc conflict / ACL isolation cases
- 用更丰富的 case family 驱动 retrieval 调优

4. online feedback
- 落地反馈采集
- 把线上失败案例稳定回灌到 eval datasets
