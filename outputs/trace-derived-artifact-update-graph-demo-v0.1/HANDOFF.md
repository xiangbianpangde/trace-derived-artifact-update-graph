# DAUG (Trace-Derived Artifact Update Graph) 开发者交接指南 (HANDOFF)

> **项目名称**：文件更新计算 (DAUG - 轨迹驱动的动态制品更新图)  
> **交接对象**：后续接手 Maintainer、核心架构师与工程研发人员  
> **当前阶段**：Phase 0 & Phase 1 已全量完成，准备启动 Phase 2 (生产辅助集成)  
> **工程状态**：**`Tested & Benchmark Verified`** (全套 24 项自动化测试 100% 通过)  
> **编写日期**：2026-09-28  

---

## 1. 交接总览 (Executive Summary)

### 1.1 项目核心定位与解决的问题
在超长程软件开发与复杂系统中，代码修改常常引发级联更新（如 API 契约、设计文档、运行手册与测试用例失效）。
- **传统静态分析缺陷**：AST 和 Import 图无法跨越代码与非代码制品（Markdown、配置）之间的语义鸿沟。
- **纯语义检索 (RAG) 短板**：只能检索“主题相似”文档，无法判断“本次接口改动究竟推翻了文档中的哪一句陈述”。
- **大模型注意力丢失**：长程 Agent 面对上下文压缩与长任务时，极易遗忘隐式更新义务。

**DAUG 创新闭环**：
1. **轨迹即观测**：提取 Agent 日常工具交互（`read`, `edit`, `search`, `test`）作为隐式依赖的在线观测信号。
2. **多源动态更新图**：融合 Git 历史、静态依赖、显式引用、语义相似度与工具行为轨迹，按变更类型（`ChangeType`）加权，负责 **Top-K 候选召回**。
3. **独立四态验证器 (Staleness Verifier)**：召回不等于失效。由独立验证器比对代码 Diff 与文档陈述（Claim Span），输出可溯源四态结论（`VALID` / `STALE` / `UNCERTAIN` / `NOT_APPLICABLE`）。
4. **CAS 补丁治理与安全网**：结合内容哈希强校验（CAS）防并发漂移，仅对 `STALE` 产生最小 Unified Diff 提案，严格隔离推荐行为防止自强化。

### 1.2 当前交付物与里程碑准出状态
- [x] **Phase 0 (只读 MVP 原型)**：完成 SQLite WAL 账本、CAS 注册、候选排序器、四态验证器与 Unified Diff 补丁生成。跑通核心契约测试（C01~C12）与场景测试（D01~D05），生成验收报告 [`reports/phase0_acceptance_report.md`](./reports/phase0_acceptance_report.md)，**通过 Gate M0 验收**。
- [x] **Phase 1 (科学基准与方法学突破)**：完成 DAUG-Bench 跨语言时间切分数据集生成器（TS/Python/Go），实现时序共变更、静态图扩展、语义检索三大对比基线；升级细粒度 Markdown Section 与符号级 Claim Span 验证器；完成大规模消融实验（Hit@1 达 100.0%，MRR 达 1.000，特异度 98.0%），生成评测报告 [`reports/phase1_benchmark_evaluation_report.md`](./reports/phase1_benchmark_evaluation_report.md)，**通过 Gate M1 验收**。
- [ ] **Phase 2 (辅助式生产环境部署)**：**[当前交接点]** 待接手团队推进 IDE 插件、后台 Daemon 守护进程与团队 A/B 灰度。

---

## 2. 接手者第一小时上手指南 (First-Hour Onboarding SOP)

请新接手的 Maintainer 在接手后按照以下步骤快速验证环境与项目健康状态：

### Step 1: 环境依赖核查 (3 分钟)
- **Node.js**：必须 `>= 22.0.0`（本项目利用 Node 22 原生 TypeScript 支持 `--experimental-strip-types` 与原生 `node:sqlite` WAL 模式，无需任何 C++ 本地编译环境）。
- **npm**：`>= 10.0.0`。
- **验证命令**：
  ```bash
  node -v   # 应输出 v22.x.x
  npm -v    # 应输出 10.x.x
  ```

### Step 2: 安装极轻量类型依赖 (1 分钟)
```bash
npm install
```

### Step 3: 执行全量自动化回归测试 (1 分钟)
```bash
npm test
```
*预期结果*：应在 200ms 内执行完毕，输出 `tests 24, suites 5, pass 24, fail 0`，全部用例无报错通过。

### Step 4: 运行 CLI 工具验证流水线 (2 分钟)
```bash
# 运行端到端示例流水线检查（导入样例轨迹、构图、召回候选、判定陈旧并提出补丁）
npm run daug -- check

# 运行 Phase 1 跨语言大规模消融评测并刷新评测报告
npm run daug -- eval
```

### Step 5: 核心代码阅读路径 (45 分钟)
建议按以下依赖顺序通读源码，快速建立完整系统认知：
1. **`src/types.ts`**：定义了工具事件 `ToolEvent`、制品 `Artifact`、图边 `GraphEdge`、候选 `UpdateCandidate`、验证结论 `VerificationResult`、补丁 `PatchProposal` 等核心契约。
2. **`src/db/index.ts`**：SQLite WAL 持久化引擎 `LedgerDb`，涵盖幂等入库（C01/C02）、外键强约束、图快照与超边存储。
3. **`src/validator/event_validator.ts`**：事件格式合法性校验、路径穿透防御（C03）与缺失前后哈希拦截（C04）。
4. **`src/cas/cas.ts`**：内容寻址存储管理器，实现并发修改哈希冲突检测（C07）。
5. **`src/graph/graph.ts` & `src/graph/ranker.ts`**：加权拓扑图构建器与 Top-K 候选排序器，关注自强化隔离（C11）与变更类型条件化加权。
6. **`src/verifier/verifier.ts` & `src/verifier/claim.ts`**：四态独立验证器与细粒度 Markdown Section / Claim Span 行级反例提取。
7. **`src/patch/patch_generator.ts`**：最小 Unified Diff 补丁生成与最小性（Minimality check）校验。
8. **`src/engine.ts`**：将上述组件统一串联的核心协调编排流水线 `DaugEngine`。

---

## 3. 关键架构设计与工程决策记录 (ADR Summary)

### ADR-01: 为什么采用 Node 22 原生能力而不是重型构建打包工具？
- **背景**：跨语言与多工具环境容易因 Node-gyp、Python 构建链或版本漂移造成环境损耗。
- **决策**：选用 Node.js 22 原生 `--experimental-strip-types` 执行 TypeScript，并使用内建 `node:sqlite`（`DatabaseSync`）与内建 `node:test` 测试运行器。
- **收益**：全库无 Webpack / Vite / ts-node / better-sqlite3 等复杂编译打包依赖，克隆即可运行，测试执行耗时从数秒降至 160ms。

### ADR-02: 为什么图只负责召回，更新必须由独立 Staleness Verifier 判定？
- **背景**：传统变更预测模型试图一步到位预测“目标文件是否应被修改”，但在局部变量重构或无关修改时极易产生高危误报。
- **决策**：严格解耦**候选召回（Candidate Retrieval）**与**陈旧验证（Staleness Verification）**。加权图只输出可能受影响的 Top-K 候选清单；独立的 Verifier 严格比对源码 Diff 与目标文档具体陈述，只有存在可证明的反例时才判定为 `STALE`。
- **收益**：在负对照（D02 场景）中实现 100% 误改拦截，大幅提升了系统的可信度与特异度。

### ADR-03: CAS 内容寻址与防漂移机制
- **背景**：在多任务或多人协作开发中，验证时看到的目标文档内容可能在生成补丁甚至用户确认的间隙发生外部变动。
- **决策**：验证器输出与补丁提案必须强制记录目标制品的 SHA-256 哈希 `expected_target_hash`。在后续任何处理环节，只要目标文件哈希发生 1 比特变动，立即触发 `HASH_CONFLICT` 熔断，强制退回重新评估。

### ADR-04: 自强化陷阱与访问权重物理分流
- **背景**：若系统推荐了某个文档给开发者/Agent，后续开发者点击查看了该文档；如果这个“推荐后的访问”被简单计入图边权重，系统将在下一轮给出更高的推荐分，形成有害的自我强化正反馈闭环。
- **决策**：在 `tool_event` 模式与 `graph_edge` 表中，严格将自发访问（`organic`）与系统推荐访问（`system_recommended`）物理分流。推荐后访问必须携带 `recommendation_id`，且赋予极低折算系数（0.05 阻尼），使单次推荐的得分增量严格低于 0.05，杜绝自证实。

---

## 4. 开发者命令速查手册 (Cheatsheet)

```bash
# ==========================================
# 自动化测试指令集
# ==========================================
# 运行全量测试套件 (包含契约测试、行为测试、引擎集成测试、Claim测试、基准测试)
npm test

# 单独运行 12 项底层核心契约测试 (C01 ~ C12)
npm run test:contract

# 单独运行 5 大场景业务行为测试 (D01 ~ D05)
npm run test:behavior

# 单独运行 Phase 1 跨语言基准数据集与对比基线测试
npm run test:benchmark

# ==========================================
# CLI 实用工具
# ==========================================
# 执行一次示例工程流水线分析 (检查变更并生成补丁提案)
npm run daug -- check

# 执行跨仓库时间切分消融评测并重新渲染评测报告
npm run daug -- eval
```

---

## 5. Phase 2 待办任务清单 (Next Maintainer Backlog)

后续接手人员可直接依据 [`ROADMAP.md`](./ROADMAP.md) 启动 **Phase 2 (辅助式生产环境部署)**，优先推进以下模块：

1. **开发 IDE 扩展插件 (VS Code Extension)**：
   - 监听编辑器保存事件，后台异步调用 `DaugEngine.runPipeline`；
   - 在侧边栏或问题面板以 L1 (Recommend) 形式提示开发者：“本次接口变更可能使 `docs/xxx.md#Lxx` 处的陈述失效”；
   - 提供浮动“查看 Diff 补丁 (L2 Propose)”按钮，支持一键对比与确认应用。
2. **构建本地 Daemon 守护进程**：
   - 将 SQLite WAL 账本与增量构图常驻后台进程，提供轻量级 IPC / Unix Domain Socket 接口，实现毫秒级响应。
3. **团队 A/B 灰度度量指标追踪**：
   - 在真实团队中接入 3 个以上日常维护项目；
   - 埋点统计补丁采纳率（Human Acceptance Rate）、陈旧文档逃逸率（Escape Rate）与开发者满意度。
4. **探索低风险资产沙箱受限写回 (L3 Sandbox Apply)**：
   - 针对完全可重新生成的 R0 级衍生制品（如从代码注释自动导出的 API 索引），在测试沙箱全绿的情况下探索自动化应用。

---

## 6. 四条绝对不可逾越的工程安全红线

在后续任何迭代或扩展中，**必须严格恪守以下四条红线**：

1. **未经授权绝对禁止写盘**：系统在默认模式下永远处于只读与补丁提案（Proposal）状态，严禁擅自修改真实源码或自动触发 Git Commit/Push。
2. **严防系统推荐自强化**：任何新引入的学习算法或权重计算，必须保持自发轨迹与推荐轨迹的分流隔离，杜绝自证实回路。
3. **CAS 内容哈希校验熔断**：任何写回或补丁确认操作必须经过目标哈希强比对，并发修改检测到哈希不符必须立即中止。
4. **不确定即停机（Fail-Safe）**：验证器遇到证据不足、模型信心低下或上下文歧义时，必须显式输出 `UNCERTAIN` 并停止自动化流程，坚决杜绝“幻觉强行修补”。
