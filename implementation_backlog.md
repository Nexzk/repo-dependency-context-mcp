# Repo + Dependency Context MCP 实施 Backlog（当前状态）

## 当前状态摘要

项目已经明显超出最初 MVP backlog，当前主线已经完成：

- MVP 主链：ingest -> retrieve -> pack -> MCP -> eval -> observability
- durable sync state：repo / GitHub metadata / vendor docs
- retrieval experimentation：candidate profiles + rerank profiles
- eval experimentation：baseline comparison + matrix run
- CLI / task / observability / playground 的实验闭环

当前更适合作为下一阶段工作导航，而不是原始 MVP 待办清单。

## 已完成阶段

### Phase 0：初始化
- [x] T-000 初始化仓库脚手架
- [x] T-001 配置系统与环境变量
- [x] T-002 日志与 tracing 基础

### Phase 1：数据库与模型
- [x] T-010 建立核心 ORM 模型
- [x] T-011 建立 Alembic 初始迁移
- [x] T-012 建立 Repository 层

### Phase 2：Repo Ingest
- [x] T-020 CLI ingest 命令
- [x] T-021 GitHub ingest service
- [x] T-022 代码 parser
- [x] T-023 Markdown parser
- [x] T-024 PR / issue / commit parser
- [x] T-025 context_prefix builder
- [x] T-026 checksum / 幂等写入

### Phase 3：索引与检索
- [x] T-030 FTS 索引
- [x] T-031 Embedding pipeline
- [x] T-032 lexical retrieval
- [x] T-033 dense retrieval
- [x] T-034 graph expansion
- [x] T-035 query normalization
- [x] T-036 task classification
- [x] T-037 hard filter 层
- [x] T-038 scoring + rerank
- [x] T-039 evidence packer
- [x] T-040 search API

### Phase 4：Dependency Docs
- [x] T-050 dependency parser
- [x] T-051 vendor domain config
- [x] T-052 vendor doc fetcher
- [x] T-053 vendor doc parser
- [x] T-054 repo dependency link

### Phase 5：MCP 与源码读取
- [x] T-060 get_source
- [x] T-061 get_related_changes
- [x] T-062 get_dependency_notes
- [x] T-063 search_context MCP 封装
- [x] T-064 MCP 鉴权

### Phase 6：评测
- [x] T-070 eval dataset schema
- [x] T-071 eval case loader
- [x] T-072 retrieval metrics
- [x] T-073 freshness / authority / ACL 指标
- [x] T-074 eval runner CLI
- [x] T-075 baseline runner

### Phase 7：内部工具与观测
- [x] T-080 playground
- [x] T-081 ingest job inspect
- [x] T-082 metrics + tracing
- [ ] T-083 feedback ingest

## 已追加完成的阶段

### Phase 8：Sync State Hardening
- [x] durable `sync_runs`
- [x] durable `sync_cursors`
- [x] local repo / GitHub metadata / vendor docs 统一 sync state
- [x] observability 中暴露 sync summaries

### Phase 9：Eval Contract Strengthening
- [x] `must_rank_before`
- [x] `expected_top_source`
- [x] per-case diagnostics
- [x] latest comparison / baseline comparison
- [x] recent failure aggregation
- [x] recent score trend

### Phase 10：Retrieval Experimentation
- [x] retrieval profile tracking
- [x] candidate profile A/B
- [x] rerank profile A/B
- [x] dual-route candidate generation
- [x] baseline-aware matrix comparison

### Phase 11：Experiment Execution Surface
- [x] eval matrix API
- [x] eval matrix CLI
- [x] eval matrix task
- [x] observability matrix summary
- [x] playground best-matrix summary
- [x] CLI output modes:
  - [x] `--json-only`
  - [x] `--table-only`
  - [x] `--best-only`
  - [x] `--failures-only`

## 下一阶段建议

### Phase 12：Related Changes 深化
- [~] 从 MVP 级匹配升级到更稳定的 change graph / reference graph
  - [x] repo-backed query expansion：`symbol -> file`、`file -> symbol`
  - [x] change ingest canonicalization：basename / known symbol -> canonical repo refs
  - [x] `get_related_changes` 返回 `match_kind` 与 `match_evidence`
  - [ ] 仍未达到完整 change graph / reference graph
- [~] 提升 PR / issue / commit 与 symbol / file 的显式关联质量
  - [x] canonical `related_file_paths`
  - [x] canonical `related_symbols`
  - [x] `linked_change_refs` graph edges + graph-link-aware tie-break

### Phase 13：Dependency Docs 深化
- [x] 从 bounded discovery 向更强的增量同步策略推进
  - [x] sync cursor 从 request-targets 升级为 vendor-doc snapshot
  - [x] cursor 现在记录 candidate set 与 content hash 快照
  - [x] basic conditional requests via ETag / Last-Modified
  - [x] page-level delta fetch
- [x] 提升 changelog / migration section 的结构化抽取
  - [x] 抽取 heading 结构
  - [x] 抽取 version headings
  - [x] 写入 `section_title` 与 `metadata_json.structure_kind`
  - [x] section-level persistence / multi-section indexing

### Phase 14：Eval Dataset 扩展
- [x] 增加 explain / debug / ambiguity / stale-doc conflict / ACL isolation cases
  - [x] explain case family
  - [x] debug case family
  - [x] ACL isolation case family
  - [x] stale-doc conflict case family
  - [x] ambiguity case family
- [ ] 扩大 demo dataset 的任务覆盖面

### Phase 15：Online Feedback
- [x] 落地 T-083 feedback ingest
- [x] 将反馈回灌成增量 eval case

## 当前发布检查
- [x] demo repo ingest 成功
- [x] 4 个 MCP 工具可用
- [x] 支持 TypeScript 和 Python
- [x] 支持 Node 和 Python 依赖解析
- [x] migration case 召回官方文档
- [x] eval runner 可运行
- [ ] Recall@10 >= 0.90（demo）
- [x] ACL Leakage = 0
- [ ] P95 latency < 3s
