# Repo + Dependency Context MCP 实施 Backlog（精简版）

## Phase 0：初始化
- T-000 初始化仓库脚手架
- T-001 配置系统与环境变量
- T-002 日志与 tracing 基础

## Phase 1：数据库与模型
- T-010 建立核心 ORM 模型
- T-011 建立 Alembic 初始迁移
- T-012 建立 Repository 层

## Phase 2：Repo Ingest
- T-020 CLI ingest 命令
- T-021 GitHub ingest service
- T-022 代码 parser
- T-023 Markdown parser
- T-024 PR / issue / commit parser
- T-025 context_prefix builder
- T-026 checksum / 幂等写入

## Phase 3：索引与检索
- T-030 FTS 索引
- T-031 Embedding pipeline
- T-032 lexical retrieval
- T-033 dense retrieval
- T-034 graph expansion
- T-035 query normalization
- T-036 task classification
- T-037 hard filter 层
- T-038 scoring + rerank
- T-039 evidence packer
- T-040 search API

## Phase 4：Dependency Docs
- T-050 dependency parser
- T-051 vendor domain config
- T-052 vendor doc fetcher
- T-053 vendor doc parser
- T-054 repo dependency link

## Phase 5：MCP 与源码读取
- T-060 get_source
- T-061 get_related_changes
- T-062 get_dependency_notes
- T-063 search_context MCP 封装
- T-064 MCP 鉴权

## Phase 6：评测
- T-070 eval dataset schema
- T-071 eval case loader
- T-072 retrieval metrics
- T-073 freshness / authority / ACL 指标
- T-074 eval runner CLI
- T-075 baseline runner

## Phase 7：内部工具与观测
- T-080 playground
- T-081 ingest job inspect
- T-082 metrics + tracing
- T-083 feedback ingest

## MVP Release Checklist
- [ ] demo repo ingest 成功
- [ ] 4 个 MCP 工具可用
- [ ] 支持 TypeScript 和 Python
- [ ] 支持 Node 和 Python 依赖解析
- [ ] migration case 召回官方文档
- [ ] eval runner 可运行
- [ ] Recall@10 >= 0.90（demo）
- [ ] ACL Leakage = 0
- [ ] P95 latency < 3s