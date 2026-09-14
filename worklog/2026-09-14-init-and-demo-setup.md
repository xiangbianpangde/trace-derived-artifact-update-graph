# Agent 工作日志：DAUG Demo 搭建与验证

- **记录日期**: 2026-09-14
- **执行 Agent**: Antigravity Assistant (接续 Codex thread `01a09d57-76e3-78f2-bf98-b159553d13db`)
- **工作目标**:
  1. 创建交接文件 `HANDOFF.md`
  2. 建立 `worklog/` 工作日志记录体系
  3. 搭建可运行的只读 DAUG (Trace-Derived Artifact Update Graph) Demo 原型系统

---

## 阶段记录

### 1. 上下文与规范对齐 (09:20)
- 检查上一轮未竟任务与中断点：上个 Agent 已完成 Markdown 文档包（10 个文档）编写与哈希校验，但在响应用户“创建交接文件handff文件用于交接，worklog文件夹用于记录agent工作日志。完成后尝试搭建这个demo”时被中断。
- 提取并冻结 Demo 设计规范：
  - 架构文档：`outputs/trace-derived-artifact-update-graph-demo-v0.1/docs/02-系统架构与数据模型.md`
  - 实施计划：`outputs/trace-derived-artifact-update-graph-demo-v0.1/docs/03-MVP与Demo实施计划.md`
  - 运行手册：`outputs/trace-derived-artifact-update-graph-demo-v0.1/docs/07-Demo运行手册与验收清单.md`
  - 数据库契约：`outputs/trace-derived-artifact-update-graph-demo-v0.1/schemas/sqlite_schema.sql` (21 张核心表)
  - 事件契约：`outputs/trace-derived-artifact-update-graph-demo-v0.1/schemas/tool_event.schema.json`

### 2. 交接文档与日志目录初始化 (09:21)
- 在项目根目录生成 `HANDOFF.md`，明确项目背景、核心边界、分级决策原则、状态机及接手指南。
- 初始化 `worklog/` 目录并建立本日志文件。

### 3. Demo 原型工程搭建 (已完成)
- 架构选型：采用 Python 3.12 原生标准库（`sqlite3`、`json`、`hashlib`、`difflib`、`re`、`pathlib`、`argparse`）实现，确保零外部依赖、高确定性与即开即用。
- 模块交付：
  - `daug/ledger.py`: SQLite WAL 账本管理，匹配 `sqlite_schema.sql` 21 张核心表，支持幂等写入、路径逃逸检测与哈希校验。
  - `daug/normalizer.py`: 轨迹事件校验、敏感信息脱敏（密钥/Token/密码）、规范化。
  - `daug/graph.py`: 融合多源证据（Trace、Static、Reference、Semantic），支持自强化抑制（organic: 1.0 vs recommended: 0.05）和大任务超边归一化（`task_hyperedge`）。
  - `daug/retriever.py`: Top-K 候选更新召回与证据解释树生成。
  - `daug/verifier.py`: 独立陈旧验证器，严格四值判定（`VALID`、`STALE`、`UNCERTAIN`、`NOT_APPLICABLE`），精确生成定位 Span。
  - `daug/patcher.py`: 最小补丁提议器，绑定目标 `expected_target_hash`，生成 unified diff 与回滚材料。
  - `daug/policy.py`: 策略引擎，执行 `propose_only` 模式与分级安全规则（R0-R4）。
  - `daug/reporter.py`: 生成 HTML 运行报告、JSON Manifest、Metrics 及 SHA-256 哈希清单。
  - `daug/cli.py` & `bin/daug`: 提供 `init`, `trace ingest`, `graph build`, `candidates rank`, `verify`, `patch propose`, `demo run` 命令行接口。
- 样例材料 (`fixtures/`):
  - `fixtures/demo-repo`: `user_context.ts`, `auth_filter.ts`, `auth_filter.test.ts`, `auth_design.md`, `api_contract.md`, `rollout_plan.md`, `auth_policy.yaml`。
  - `fixtures/changes`: A (接口变更), B (局部重构负对照), C (批量格式化超边), D (推荐访问诱导)。
  - `fixtures/traces`: `organic-interface-change.jsonl`, `assisted-unrelated-read.jsonl`。
  - `fixtures/labels/gold.json` & `fixtures/manifests/demo-manifest.json`。

### 4. 契约与行为测试验证 (09:25)
- 编写自动化测试套件：
  - `tests/test_contracts.py`: 验证 C01（幂等去重）、C02（哈希冲突）、C03（路径越界拒绝）、C04（不完整哈希标记）、C05（推荐缺少ID拒绝）、C06（图摘要确定性）、C07（目标哈希漂移拦截）、C09（受保护资产安全拦截）、C10（批量任务超边避免边爆炸）。
  - `tests/test_demo_scenarios.py`: 验证 D01（接口变更召回并判定 STALE）、D02（局部重构负对照 0 误报）、D06（提示词注入安全隔离）。
- 测试结果：
  ```text
  Ran 12 tests in 0.527s
  OK (12 passed, 0 failed, 0 error)
  ```

### 5. 端到端 Demo 演练验收 (09:26)
- 执行命令：`./bin/daug demo run`
- 运行产物归档于 `runs/demo-run-20260914-012526/`：
  - `report.html`: 交互式运行报告
  - `run_manifest.json`: 完整元数据清单
  - `candidate_sets.jsonl`: 候选集与特征证据
  - `verifications.jsonl`: 验证结论与 Span 定位
  - `patch_proposals/`: 最小补丁 unified diff
  - `hashes.sha256`: 全产物哈希清单
- 演示状态词宣布：
  - Event ingestion: **Tested**
  - Offline replay: **Tested**
  - Candidate ranking: **Tested on demo fixture**
  - Staleness verification: **Tested on synthetic fixture**
  - Patch application: **Not implemented (Strictly Propose Only)**
  - Production enablement: **Not authorized**

