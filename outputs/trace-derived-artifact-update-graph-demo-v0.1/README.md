# 轨迹驱动的动态制品更新图 (DAUG) 技术方案与工程实现包

> **Trace-Derived Artifact Update Graph (DAUG)**  
> **版本**：v0.1  
> **工程成熟度**：**`Tested & Benchmark Verified`** (全套 24 项自动化测试 100% 通过)  
> **当前阶段**：Phase 0 (MVP 只读闭环) & Phase 1 (科学基准评测) 已全量完成，进入 Phase 2 准备阶段  
> **更新日期**：2026-09-28  

---

## 核心主旨

本方案旨在解决超长程 AI Agent 在长期维护大型项目时面临的“**隐式更新义务丢失与文档/代码漂移**”难题。

传统静态分析无法触及设计文档与配置文件，而语义检索（RAG）又无法判断具体哪一句陈述已被代码改动推翻。DAUG 将 Agent 日常开发中的工具交互轨迹（`read`、`search`、`edit`、`write`、`test`）作为动态依赖的在线观测信号，结合 Git 历史、静态依赖、显式引用和语义向量，构建有方向、带变更类型（`ChangeType`）的 Artifact Update Graph。

变更发生后，图负责召回可能受影响的制品；独立的 **Staleness Verifier** 比对代码 Diff 与陈述，判断具体陈述是否失效。系统通过 CAS 内容哈希强校验与分级写回策略，确保安全性。

---

## 快速导航与核心入口

| 维度 | 文档链接 | 说明 |
| :--- | :--- | :--- |
| **交接必读** | 🤝 **[`HANDOFF.md`](./HANDOFF.md)** | **开发者交接指南**、第一小时上手 SOP、架构决策与 Phase 2 待办 |
| **全库索引** | 📚 **[`INDEX.md`](./INDEX.md)** | **全量文件注册表**、目录职责、关键概念与源码映射字典 |
| **演进规划** | 🗺️ **[`ROADMAP.md`](./ROADMAP.md)** | Phase 0 ~ Phase 3 四阶段技术演化路线图、学术规划与红线 |
| **技术规范** | 🏛️ **[`docs/`](./docs/)** | 包含总体方案 (01)、系统架构 (02)、实施排期 (03)、评测消融 (04)、风险治理 (05)、论文规划 (06)、验收手册 (07) |
| **验收报告** | 📊 **[`reports/`](./reports/)** | Phase 0 结项验收报告 (Gate M0) 与 Phase 1 跨仓库消融评测报告 (Gate M1) |
| **数据契约** | 📐 **[`schemas/`](./schemas/)** | SQLite WAL 模式 DDL (`sqlite_schema.sql`) 与工具事件规范 (`tool_event.schema.json`) |
| **核心源码** | 💻 **[`src/`](./src/)** | 包含引擎 (`engine.ts`)、账本 (`db/`)、加权图 (`graph/`)、验证器 (`verifier/`) 与基准 (`benchmark/`) |
| **历史归档** | 📦 **[`archive/`](./archive/)** | 历史里程碑快照、v0.1 单文件大合订版与原校验签名清单 |

---

## 核心架构图解

| 系统总体架构 | 数据模型与实体关系 | 更新生命周期状态机 |
| :---: | :---: | :---: |
| ![][arch-img] | ![][model-img] | ![][cycle-img] |
| [查看高清矢量图][arch-svg] | [查看高清矢量图][model-svg] | [查看高清矢量图][cycle-svg] |

[arch-img]: assets/system-architecture.png
[arch-svg]: assets/system-architecture.svg
[model-img]: assets/data-model.png
[model-svg]: assets/data-model.svg
[cycle-img]: assets/update-lifecycle.png
[cycle-svg]: assets/update-lifecycle.svg

---

## 快速启动与命令速查

```bash
# 1. 安装极轻量类型依赖 (利用 Node 22 原生能力，零 C++ 本地编译)
npm install

# 2. 运行全量 24 项自动化测试套件 (包含底层契约、行为场景、集成流水线、Claim验证与基准对比)
npm test

# 3. 运行端到端流水线检查（导入样例事件流，执行构图、召回、验证并生成补丁）
npm run daug -- check

# 4. 运行跨语言时间切分大规模消融实验并自动刷新评测报告
npm run daug -- eval
```

---

## 项目完整目录结构

```text
文件更新计算 (DAUG-Project)/
├── .gitignore                          # Git 忽略配置
├── README.md                           # 项目白皮书、总览与导航入口
├── ROADMAP.md                          # 四阶段演进路线图 (Phase 0 ~ Phase 3)
├── HANDOFF.md                          # [交接必读] 完整交接指南与第一小时上手 SOP
├── INDEX.md                            # 全库资产与文件总索引字典
├── package.json                        # Node.js 工程配置与 npm 脚本
├── tsconfig.json                       # TypeScript 编译器配置
│
├── docs/                               # 核心技术方案与规范（模块化分册）
│   ├── 01-总体技术方案.md                 # 核心问题、机制创新与理论定义
│   ├── 02-系统架构与数据模型.md            # 系统五层架构、状态机与存储模型
│   ├── 03-MVP与Demo实施计划.md           # 四周实施排期、验收测试集与样例场景
│   ├── 04-评测与消融实验方案.md            # 离线评测、消融对比与偏差控制
│   ├── 05-风险与治理.md                  # 安全红线、CAS 防漂移与三级写回策略
│   ├── 06-后续研发与论文规划.md            # 科学方法学、跨仓库基准与学术路线
│   └── 07-Demo运行手册与验收清单.md        # 演示运行步骤、输入输出与验收清单
│
├── schemas/                            # 机器可读数据契约与存储模式
│   ├── sqlite_schema.sql               # SQLite WAL 存储 DDL（账本、制品、图边、补丁）
│   └── tool_event.schema.json          # Agent 工具轨迹通用 JSON Schema 契约
│
├── src/                                # 核心引擎源码实现 (TypeScript)
│   ├── types.ts                        # 全局类型定义与 SHA-256 工具
│   ├── engine.ts                       # 流水线统一协调编排引擎 (DaugEngine)
│   ├── cli.ts                          # 命令行交互工具入口 (`daug check` / `daug eval`)
│   ├── db/                             # SQLite 账本持久化与事务管理
│   ├── validator/                      # 事件模式校验与路径穿透拦截
│   ├── cas/                            # 内容寻址存储 (CAS) 与并发漂移熔断检测
│   ├── trace/                          # JSONL 事件流导入与回放器
│   ├── graph/                          # 动态加权图构建与 Top-K 候选排序器
│   ├── verifier/                       # 四态独立验证器与细粒度 Claim Span 证明
│   ├── patch/                          # CAS 绑定 Unified Diff 补丁生成与最小性检查
│   └── benchmark/                      # DAUG-Bench 跨语言基准集、强基线与评估器
│
├── tests/                              # 全自动化测试套件 (24/24 PASS)
│   ├── contract.test.ts                # 12 项核心底层契约测试 (C01 ~ C12)
│   ├── behavior.test.ts                # 5 大业务场景行为测试 (D01 ~ D05)
│   ├── engine.test.ts                  # 端到端核心流水线集成测试
│   ├── claim_verifier.test.ts          # Section 树与行级 Claim Span 细粒度测试
│   └── benchmark.test.ts               # 时间切分防泄露与跨语言基线测试
│
├── reports/                            # 自动化生成的正式验收与评测报告
│   ├── phase0_acceptance_report.md     # Phase 0 MVP 只读结项验收报告 (Gate M0 PASS)
│   └── phase1_benchmark_evaluation_report.md # Phase 1 科学基准消融实验报告 (Gate M1 PASS)
│
├── examples/                           # 样例轨迹与策略配置模板
│   ├── demo_trace.jsonl                # 样例工具调用事件流
│   └── policy.example.yaml             # 风险分级与写回策略模板
│
├── assets/                             # 架构设计、数据流与生命周期高清图元
│   ├── README.md                       # 资产目录规范说明
│   ├── system-architecture.svg / .png  # 系统总体架构图 (4000x2050)
│   ├── data-model.svg / .png           # 数据模型与实体关系图 (4000x2150)
│   ├── update-lifecycle.svg / .png     # 更新生命周期状态机图 (4000x1800)
│   └── explainer/                      # 宣传推介与概念讲解海报
│
├── references/                         # 理论依据与学术参考文献
│   └── 参考资料.md                      # 变更耦合、依赖分析、文档陈旧检测等文献
│
└── archive/                            # 历史版本与基准签名归档
    ├── README.md                       # 归档说明与元数据索引
    └── v0.1/                           # v0.1 方案初版合订历史快照与原签名
```

---

## 核心边界与不可逾越的红线

1. **相关性不等于陈旧，陈旧不等于写回**：图推荐只触发检查，只有独立验证器判定 `STALE` 且附带证据后才进入治理流程。
2. **严防推荐自强化**：自发交互轨迹（Organic）与推荐交互轨迹（Assisted）物理分流记录，推荐点击绝不反向推高边权。
3. **CAS 内容哈希强校验**：每次生成补丁必须绑定目标文件的 SHA-256 哈希；一旦检测到并发变动立即熔断。
4. **受保护制品禁止自动应用**：部署配置、安全策略、法律合规文本、科研核心结论等高风险资产严禁自动写回。
5. **不确定即停机（Fail-Safe）**：验证器返回 `UNCERTAIN` 时必须终止后续自动化流程，转交人工审查。
