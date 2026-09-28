# DAUG (Trace-Derived Artifact Update Graph) 全库资产与文件总索引

> **项目名称**：文件更新计算 (DAUG - 轨迹驱动的动态制品更新图)  
> **文档定位**：全库工程文件、架构规范、数据模式、源码实现及测试报告的完整索引字典。  
> **更新日期**：2026-09-28  
> **当前状态**：Phase 0 & Phase 1 已全量完成 (Tested & Benchmark Verified)  

---

## 1. 核心导航与快速入口

| 目标读者 | 推荐入口 | 核心关注点 |
| :--- | :--- | :--- |
| **新接手开发者 / Maintainer** | 🤝 **[`HANDOFF.md`](./HANDOFF.md)** | **第一小时上手指南**、架构精要、命令手册与 Phase 2 待办 |
| **业务 / 项目负责人** | 🗺️ **[`ROADMAP.md`](./ROADMAP.md)** | 四阶段路线图、里程碑交付物与安全红线 |
| **系统架构师 / 科研人员** | 🏛️ **[`README.md`](./README.md)** & [`docs/`](./docs/) | 全链路技术原理、数学定义、数据模型与评测消融 |
| **审计与质量把关** | 📊 **[`reports/`](./reports/)** | Phase 0 (Gate M0) 与 Phase 1 (Gate M1) 结项评测报告 |

---

## 2. 仓库全景目录树 (Repository Tree)

```text
文件更新计算/
├── .gitignore                          # Git 忽略配置（忽略 node_modules、本地日志及缓存）
├── README.md                           # 项目白皮书、总览与图解入口
├── ROADMAP.md                          # 四阶段演进路线图 (Phase 0 ~ Phase 3)
├── HANDOFF.md                          # [交接必读] 完整交接指南与第一小时上手 SOP
├── INDEX.md                            # [本文件] 全库资产与文件总索引
├── package.json                        # Node.js 工程配置与 npm 脚本定义
├── tsconfig.json                       # TypeScript 编译器配置 (ES2022 / NodeNext)
│
├── docs/                               # 核心技术方案与规范（模块化分册）
│   ├── 01-总体技术方案.md                 # 核心问题形式化、理论模型与总体设计
│   ├── 02-系统架构与数据模型.md            # 五层系统架构、状态转换机与存储拓扑
│   ├── 03-MVP与Demo实施计划.md           # 四周实施排期、契约测试 (C01~C12) 与场景定义
│   ├── 04-评测与消融实验方案.md            # 离线评测设计、消融实验与自强化控制
│   ├── 05-风险与治理.md                  # 安全红线、CAS 内容寻址防漂移与分级写回
│   ├── 06-后续研发与论文规划.md            # 跨仓库科学基准与顶级学术会议规划
│   └── 07-Demo运行手册与验收清单.md        # 演示运行步骤、输入输出与阶段验收清单
│
├── schemas/                            # 机器可读数据契约与持久化模式
│   ├── sqlite_schema.sql               # SQLite WAL 模式 DDL（账本、制品、图边、补丁）
│   └── tool_event.schema.json          # Agent 工具轨迹通用 JSON Schema 规范
│
├── src/                                # 核心引擎源码实现 (TypeScript)
│   ├── types.ts                        # 全局类型定义与 SHA-256 辅助函数
│   ├── engine.ts                       # 流水线统一协调编排引擎 (DaugEngine)
│   ├── cli.ts                          # 命令行交互工具入口 (`daug check` / `daug eval`)
│   ├── db/                             # 存储底座层
│   │   └── index.ts                    # SQLite 账本管理类 (LedgerDb)，支持 WAL 与事务
│   ├── validator/                      # 契约校验层
│   │   └── event_validator.ts          # 工具事件校验器，拦截路径穿透与哈希缺失
│   ├── cas/                            # 内容寻址存储层 (Content-Addressed Storage)
│   │   └── cas.ts                      # 制品内容哈希追踪与并发漂移熔断检测
│   ├── trace/                          # 轨迹处理层
│   │   └── importer.ts                 # JSONL 轨迹文件流式解析与批量导入器
│   ├── graph/                          # 动态拓扑图层
│   │   ├── graph.ts                    # 多源加权图构建器 (ArtifactUpdateGraph)，自强化隔离
│   │   └── ranker.ts                   # Top-K 候选排序器 (CandidateRanker)，变更类型加权
│   ├── verifier/                       # 独立陈旧性验证层
│   │   ├── verifier.ts                 # 四态独立验证器 (StalenessVerifier: VALID/STALE/...)
│   │   └── claim.ts                    # 细粒度 Claim Span 锚点解析器与行级反例验证器
│   ├── patch/                          # 补丁治理层
│   │   └── patch_generator.ts          # CAS 绑定 Unified Diff 补丁生成与最小性检查
│   └── benchmark/                      # 科学基准评测层 (Phase 1)
│       ├── dataset_generator.ts        # DAUG-Bench 跨语言时间切分数据集生成器 (TS/Py/Go)
│       ├── baselines.ts                # 时序共变、静态调用图、语义检索三大对比基线
│       └── evaluator.ts                # Hit@K, MRR, 精度, 召回与特异度科学评测器
│
├── tests/                              # 全自动化测试套件 (24/24 PASS)
│   ├── contract.test.ts                # 12 项核心底层契约测试 (C01 ~ C12)
│   ├── behavior.test.ts                # 5 大业务场景与行为测试 (D01 ~ D05)
│   ├── engine.test.ts                  # 端到端核心流水线集成测试
│   ├── claim_verifier.test.ts          # Section 树与行级 Claim Span 细粒度验证测试
│   └── benchmark.test.ts               # DAUG-Bench 时间切分与基线对比自动化测试
│
├── scripts/                            # 自动化脚本与评测执行器
│   └── run_evaluation.ts               # 运行全量跨仓库消融评测并自动生成评测报告
│
├── reports/                            # 自动化生成的正式验收与评测报告
│   ├── phase0_acceptance_report.md     # Phase 0 MVP 只读闭环结项报告 (Gate M0 PASS)
│   └── phase1_benchmark_evaluation_report.md # Phase 1 科学基准消融实验报告 (Gate M1 PASS)
│
├── examples/                           # 样例数据与策略配置模板
│   ├── demo_trace.jsonl                # 包含 8 条典型工具调用事件的样例轨迹
│   └── policy.example.yaml             # 制品风险分类与写回策略模板
│
├── assets/                             # 架构设计与状态机图元资产
│   ├── README.md                       # 资产使用与归档规范
│   ├── system-architecture.svg / .png  # 系统总体架构图 (4000x2050)
│   ├── data-model.svg / .png           # 数据模型与实体关系图 (4000x2150)
│   ├── update-lifecycle.svg / .png     # 更新生命周期状态机图 (4000x1800)
│   └── explainer/                      # 宣传推介与概念讲解海报 (多语言/多尺寸)
│       ├── daug-project-explainer-zh.png
│       ├── daug-project-explainer.png
│       └── project_explainer_cn.jpg
│
├── references/                         # 理论参考与学术文献
│   └── 参考资料.md                      # 变更耦合、依赖分析、文档陈旧检测等文献综述
│
└── archive/                            # 历史里程碑快照归档
    ├── README.md                       # 归档版本元数据与说明
    └── v0.1/                           # 2026-09-14 初版合订大文件与原签名清单
        ├── Trace-Derived-Artifact-Update-Graph-Demo-技术方案-v0.1.md
        └── MANIFEST.sha256
```

---

## 3. 全量文件职责与状态注册表 (File Registry)

| 文件路径 | 类型 | 职责说明 | 所属阶段 | 稳定性 |
| :--- | :--- | :--- | :--- | :---: |
| `README.md` | 文档 | 项目白皮书、总览入口、架构图解 | Phase 0~3 | 稳定 |
| `ROADMAP.md` | 文档 | 四阶段演进路线图、技术矩阵与红线 | Phase 0~3 | 稳定 |
| `HANDOFF.md` | 文档 | 开发者交接指南、上手 SOP、命令手册 | Phase 0~3 | 稳定 |
| `INDEX.md` | 文档 | 全库资产、文件与职责总索引字典 | Phase 0~3 | 稳定 |
| `docs/01-总体技术方案.md` | 方案 | 问题形式化、核心概念模型、理论推导 | Phase 0 | 稳定 |
| `docs/02-系统架构与数据模型.md` | 方案 | 五层架构、状态机模型、SQLite DDL 解析 | Phase 0 | 稳定 |
| `docs/03-MVP与Demo实施计划.md` | 方案 | 4周实施排期、C01~C12 契约、样例设计 | Phase 0 | 稳定 |
| `docs/04-评测与消融实验方案.md` | 方案 | 离线评测、消融基线、特异度与指标定义 | Phase 0/1 | 稳定 |
| `docs/05-风险与治理.md` | 方案 | 安全红线、CAS 防漂移、分级写回策略 | Phase 0~3 | 稳定 |
| `docs/06-后续研发与论文规划.md` | 方案 | 跨仓库基准、学术论文规划与多 Agent | Phase 1~3 | 稳定 |
| `docs/07-Demo运行手册与验收清单.md`| 方案 | 演示步骤、输入输出规范与验收 Checklist | Phase 0 | 稳定 |
| `schemas/sqlite_schema.sql` | 契约 | SQLite WAL 账本 DDL 架构（核心表定义） | Phase 0 | 冻结 |
| `schemas/tool_event.schema.json` | 契约 | Agent 工具事件通用 JSON Schema 规范 | Phase 0 | 冻结 |
| `src/types.ts` | 源码 | 核心 TypeScript 类型定义与哈希工具 | Phase 0 | 稳定 |
| `src/engine.ts` | 源码 | 流水线统一协调编排引擎 (DaugEngine) | Phase 0 | 稳定 |
| `src/cli.ts` | 源码 | 命令行交互入口 (`daug check`, `daug eval`) | Phase 0/1 | 稳定 |
| `src/db/index.ts` | 源码 | SQLite WAL 存储引擎 (LedgerDb)，支持事务 | Phase 0 | 稳定 |
| `src/validator/event_validator.ts` | 源码 | 工具事件模式校验器与安全路径拦截 | Phase 0 | 稳定 |
| `src/cas/cas.ts` | 源码 | 内容寻址存储注册表与并发哈希校验 | Phase 0 | 稳定 |
| `src/trace/importer.ts` | 源码 | JSONL 格式事件流导入与回放器 | Phase 0 | 稳定 |
| `src/graph/graph.ts` | 源码 | 动态加权图构建器，支持超边与自强化隔离 | Phase 0 | 稳定 |
| `src/graph/ranker.ts` | 源码 | Top-K 候选排序器，支持变更类型调节 | Phase 0 | 稳定 |
| `src/verifier/verifier.ts` | 源码 | 四态独立陈旧性验证器与 Diff 符号差分 | Phase 0 | 稳定 |
| `src/verifier/claim.ts` | 源码 | Markdown Section 树解析与行级反例验证 | Phase 1 | 稳定 |
| `src/patch/patch_generator.ts` | 源码 | CAS 绑定 Unified Diff 补丁生成器 | Phase 0 | 稳定 |
| `src/benchmark/dataset_generator.ts`| 源码 | 跨语言时间切分基准数据集生成器 | Phase 1 | 稳定 |
| `src/benchmark/baselines.ts` | 源码 | 时序共变、静态图扩展、语义检索对比基线 | Phase 1 | 稳定 |
| `src/benchmark/evaluator.ts` | 源码 | 科学指标评估器 (Hit@K, MRR, 特异度) | Phase 1 | 稳定 |
| `tests/contract.test.ts` | 测试 | 12 项底层核心契约测试 (C01~C12) | Phase 0 | 12/12 PASS |
| `tests/behavior.test.ts` | 测试 | 5 大业务场景行为测试 (D01~D05) | Phase 0 | 5/5 PASS |
| `tests/engine.test.ts` | 测试 | 流水线端到端完整闭环测试 | Phase 0 | PASS |
| `tests/claim_verifier.test.ts` | 测试 | Section 树与行级 Claim Span 细粒度测试 | Phase 1 | 3/3 PASS |
| `tests/benchmark.test.ts` | 测试 | 时间切分防泄露与跨语言基线测试 | Phase 1 | 3/3 PASS |
| `scripts/run_evaluation.ts` | 脚本 | 全量消融实验运行并自动渲染报告脚本 | Phase 1 | 稳定 |
| `reports/phase0_acceptance_report.md` | 报告 | Phase 0 MVP 只读结项验收报告 (Gate M0) | Phase 0 | 已归档 |
| `reports/phase1_benchmark_evaluation_report.md` | 报告 | Phase 1 跨仓库基准评测报告 (Gate M1) | Phase 1 | 已归档 |
| `examples/demo_trace.jsonl` | 示例 | 真实工具事件流水线演示数据样例 | Phase 0 | 稳定 |
| `examples/policy.example.yaml` | 示例 | 制品风险分级策略与写回规则模板 | Phase 0 | 稳定 |
| `archive/v0.1/*` | 归档 | 2026-09-14 历史单文件合订版方案与哈希清单 | 历史 | 归档只读 |

---

## 4. 关键概念与对应实现映射表

| 概念名称 | 说明 | 对应模式/类型 | 核心源码位置 | 关键测试验证 |
| :--- | :--- | :--- | :--- | :--- |
| **ToolEvent** | Agent 工具交互原子事件 | `schemas/tool_event.schema.json` | `src/validator/event_validator.ts` | `tests/contract.test.ts` (C01~C05) |
| **LedgerDb** | SQLite WAL 事件与图账本 | `schemas/sqlite_schema.sql` | `src/db/index.ts` | `tests/contract.test.ts` (C01, C06, C12) |
| **CAS 强校验** | 内容寻址哈希防并发漂移 | `ArtifactVersion` | `src/cas/cas.ts` | `tests/contract.test.ts` (C07) |
| **UpdateGraph** | 加权动态制品更新图 | `GraphEdge`, `GraphSnapshot` | `src/graph/graph.ts` | `tests/contract.test.ts` (C06, C10, C11) |
| **Ranker** | 多源特征融合候选排序器 | `UpdateCandidate` | `src/graph/ranker.ts` | `tests/behavior.test.ts` (D01, D03) |
| **4-State Verifier**| 独立四态陈旧验证器 | `VerificationResult` | `src/verifier/verifier.ts` | `tests/contract.test.ts` (C08), `tests/engine.test.ts` |
| **Claim Span** | 细粒度行级陈述反例证明 | `DetailedClaimSpan` | `src/verifier/claim.ts` | `tests/claim_verifier.test.ts` |
| **Patch Proposal** | 最小 Unified Diff 提案 | `PatchProposal` | `src/patch/patch_generator.ts` | `tests/behavior.test.ts` (D01, D02) |
| **Temporal Split** | 时间切分防未来泄露基准 | `BenchmarkCase` | `src/benchmark/dataset_generator.ts` | `tests/benchmark.test.ts` |
| **Baselines** | 强非轨迹对比基线 | `BaselineRunner` | `src/benchmark/baselines.ts` | `tests/benchmark.test.ts`, `scripts/run_evaluation.ts` |
