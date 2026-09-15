# 论文 B 详细规划：从变更预测到安全可信的文档维护 (Paper B Plan)

**题目预案**: *From Change Prediction to Verified Artifact Maintenance: Governed Human-in-the-Loop Documentation Consistency for Software Agents*  
**阶段定位**: P2 阶段核心理论与工程方法学沉淀  
**核心关注**: 独立验证器、四值语义状态机、选择性放弃 (Selective Abstention) 与 CAS 内容寻址安全门禁  
**日期**: 2026-09-15  

---

## 1. 核心研究命题

在长程 Agent 编程中，仅能召回受影响制品（Candidate Retrieval）并不能直接转化为安全可靠的维护建议。相关性并不等同于修改义务。传统“大模型全自动直接写回”的粗暴模式极易导致以下三大灾难：

1. **幻觉写回与过度维护 (Over-eager Updates)**：对于局部重构（如性能优化、内部变量重命名），代码语义并未向外扩散，直接写回会导致文档产生虚假变更；
2. **锚点漂移与覆盖写坏 (Out-of-band Overwrite Drift)**：在多人或并发 Agent 协作中，若文档已被他人更新，自动化补丁覆盖将导致不可逆的代码与知识丢失；
3. **警报疲劳与信任崩塌 (Alert Fatigue)**：频繁、低置信度的弱相关提醒会迫使人类开发者关闭维护机制。

**论文 B 核心命题**：  
> **通过解耦“候选检索”与“独立陈旧验证”，结合陈述级细粒度锚点（Section/Pointer）、选择性放弃机制（Selective Abstention）与 CAS 哈希前置条件，能够在保证零虚假更新的前提下，显著降低人类审查与合并陈旧补丁的认知负荷。**

---

## 2. 四值验证语义与状态迁移规范

传统分类器强行在“陈旧 (Stale)”与“有效 (Valid)”之间进行二分类，掩盖了证据不足与领域不适用的本质区别。论文 B 确立四值验证语义：

```text
               ┌──────────────────────────┐
               │    Update Candidate      │
               └─────────────┬────────────┘
                             │
                     [ Staleness Verifier ]
                             │
         ┌──────────────┬────┴─────────────┬─────────────────┐
         ▼              ▼                  ▼                 ▼
     [ VALID ]      [ STALE ]         [ UNCERTAIN ]    [ NOT_APPLICABLE ]
   (负对照/一致)  (发现漂移符号/陈述) (证据不足/冲突)   (与变更契约完全无关)
         │              │                  │                 │
      [ 归档 ]    [ 生成 Diff 补丁 ]    [ 人工复核 ]       [ 归档 ]
                        │
            [ CAS Precondition Guard ]
                        │
           [ Single-use Approval Gate ]
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
        [ Applied ]           [ Rejected ]
    (CAS校验通过并写入)   (开发者人工否决/推迟)
```

1. **`VALID`**：经验证代码改动在目标文件覆盖范围内保持一致（如局部重构或同义修饰），系统记录依据并静默通过。
2. **`STALE`**：明确匹配到过时字段或破坏性契约，且能够定位到细粒度章节或指针，自动生成最小 Unified Diff 提案。
3. **`UNCERTAIN`**：置信度低于阈值 $\theta_{conf} = 0.85$ 或存在互相矛盾的轨迹信号，系统主动放弃自动提案（Abstain），转为标注提示供开发者决策。
4. **`NOT_APPLICABLE`**：虽然同处一个任务工作区，但目标制品（如部署脚本、环境配置）与该变更类型不存在契约交集。

---

## 5. 陈述级陈旧的两个正交类别：符号漂移与状态漂移

P0/P1 阶段的陈旧验证器建立在**符号漂移（symbol drift）**检测之上：当代码中的标识符被重命名或删除（如 `user_id` → `subject_id`），验证器在文档中查找该符号的遗留引用并定位具体陈述。该机制在结构化引用上表现良好，但存在一个此前未被识别的盲区。

### 5.1 盲区：无符号变化的状态漂移

在真实的长程 Agent 协作中，第二类陈旧频繁发生，却**不涉及任何标识符变化**：

1. **状态跃迁（state transition）**：状态账本（如 `plan/STATUS.md`）将某工作单元从 `review` 推进为 `active`。另一份文档（如 `HANDOFF.md`）此前断言「WU-0013 正在审计中」。该散文陈述现已为假，但它与代码差异没有任何共享标识符，符号匹配永远不会触发。
2. **数值断（numeric claim）**：某交接文档写明「Plan revision: 60」，而计划实际已推进至 revision 104。没有任何符号改变，只有一个数字。

这两类漂移的共同特征是：**陈述的真值依赖于另一个权威制品的当前状态，而非其文本内容**。因此，检测它们要求系统显式建模「真值源（source of truth）」，而不能仅做文本相似度比对。

### 5.2 方法：真值源锚定的状态断言验证

DAUG 将该盲区形式化为**状态断言验证（state-claim verification）**问题：

> 给定一个被指定为真值源的账本制品 $a_{truth}$，以及任意文档 $a_{t}$ 中的状态断言 $\phi$，判定 $\phi$ 是否与 $a_{truth}$ 的当前状态一致。

实现分为三个组成部分（`daug/statecheck.py`）：

**（1）真值抽取（StateTruthExtractor）**
- 从账本 frontmatter 提取单调递增的 `revision` 计数器；
- 解析 Markdown 状态表，将工作单元 ID 映射到状态词。
- **列位置无关**：状态列通过表头名称（`状态`/`status`/`state`）定位而非固定索引，使解析器在列重排后仍然有效。

**（2）邻接配对（nearest-preceding binding）**

关键的工程约束来自首个真实运行中观察到的**误报**。同一行常同时提及多个状态各异的工作单元：

```
第二阶段 WU-0011 与 WU-0012 均已置为 verified；WU-0013 处于 active，等待放行。
```

若将每个工作单元与行内**第一个**状态词配对，会错误地将 `verified` 归属给 `WU-0013`（该行实际称其 `active`）。正确的语义是：**状态词归属于其最近的、出现在其之前的工作单元**。出现在任何工作单元之前的状态词不构成任何断言，应被丢弃。该约束将误报从 1 降至 0。

**（3）选择性收敛与放弃（scoped abstention）**

与四值验证语义一致，状态检测器遵循两条收敛规则，防止将合法历史误判为陈旧：

- **数值断言仅在协调类文档的头部区域检查**（前 120 行）。正文中的历史 revision 数字是正当的历史记录，不是陈旧断言。
- **无法自信解析即放弃**：若真值源不可读或数值无法解析，检测器**不产生任何断言**，而非猜测。

检测结果以新的原因码 `STALE_STATE_CLAIM` 输出，与符号漂移的 `OBSOLETE_SYMBOL_REFERENCE` 在证据层明确区分。

### 5.3 真实仓库验证结果

在真实项目（`GAP Context Pager skills`，135 个追踪制品）上首次运行该检测器，即刻捕获两处**长期存在且此前完全不可见**的陈旧断言：

| 位置 | 文档断言 | 真值 | 偏差 |
| --- | --- | --- | --- |
| `HANDOFF.md:5` | `plan/STATUS.md` revision **74** | revision **104** | 30 |
| `HANDOFF.md:62` | `Plan revision: **60**` | revision **104** | 44 |

修复后重跑，检测器报告 **0 陈旧断言**，确认文档已与真值源收敛。这一结果同时验证了两件事：检测器在真实数据上具有**有效增益**（发现符号匹配永远无法发现的问题），并且在修复后**不产生残余误报**。

### 5.4 与符号漂移的互补关系

| 维度 | 符号漂移 | 状态漂移 |
| --- | --- | --- |
| 触发条件 | 标识符重命名/删除 | 权威状态值变化 |
| 证据来源 | 代码 diff | 真值源制品的当前状态 |
| 锚点形式 | `section:` / `symbol:` / `json_pointer:` | `line:` + 真值对比 |
| 原因码 | `OBSOLETE_SYMBOL_REFERENCE` | `STALE_STATE_CLAIM` |
| 典型盲区 | — | 状态推进、计数器递增 |

两类检测共同构成**陈述级（claim-level）**陈旧覆盖的自然完备性：符号漂移覆盖「文本引用了已不存在的符号」，状态漂移覆盖「文本断言了已过期的状态」。二者共享同一套治理约束（细粒度锚点、CAS 前置条件、人工门禁、选择性放弃），不引入额外的写回风险。

---

## 6. 人机协同辅助部署 (P2 Deployment) 架构

### 3.1 交互式 Web 审查工作台 (`daug review`)
- **零依赖架构**：基于标准库 `http.server` 构建的现代化暗色工作台，无需构建或安装大型 Web 环境，开箱即用。
- **分栏 Diff (Side-by-Side Diff)**：高亮展示陈旧章节锚点（`section:## Header > item`）与对应生成的精确增删差异。
- **单次批准门禁 (Single-use Approval Gate)**：
  - 开发者通过 Web 界面逐项审阅补丁并点击 `Apply Patch`；
  - 后端严格执行 CAS 预检（`current_sha256 == expected_target_hash`）；
  - 若检测到外部并发修改即刻触发 `HashConflictError` 阻断写入；
  - 写入完成后即刻执行回读 SHA-256 校验，并在 SQLite WAL 账本中签发审计回执（`application_receipt`）。

### 3.2 宿主 Agent 深度协同 (`/daug review`)
- 在 Pi Coding Agent 环境中，开发者随时可以通过 `/daug review` 唤起本地工作台；
- Agent 在执行写入工具时，通过 `daug_check` 获取结构化过时诊断，并在上下文注入安全告警，杜绝盲目写回。

---

## 7. 评测协议与实验设计 (P2 Evaluation Protocol)

1. **接受率 (Acceptance Rate, AR)**：
   $$\text{AR} = \frac{\text{Accepted Patches}}{\text{Proposed Patches}}$$
   目标：在真实开发环境下达到 $\text{AR} \ge 80\%$。
2. **审查耗时节约 (Triage Time Reduction)**：
   对比人类手动排查各级关联文档所需时间与基于 `daug review` 分栏界面的确认耗时，目标降低 $\ge 70\%$ 的排查时间。
3. **零破坏写入保证 (Zero Silent Drifts)**：
   在 CAS 保护下，任何外部修改或并发冲突的未授权写回发生率为严格的 **0.0%**。

---

## 8. 阶段交付物矩阵

| 交付模块 | 对应路径 | 交付状态 |
|---|---|---|
| 交互式 Web 审查服务器 | [`daug/server.py`](daug/server.py) | **Implemented & Tested** |
| CLI `daug review` 命令 | [`daug/cli.py`](daug/cli.py) | **Implemented & Ready** |
| Web 服务自动化单测 | [`tests/test_review_server.py`](tests/test_review_server.py) | **Passed (100%)** |
| Pi Agent `/daug review` 扩展 | [`extensions/daug.ts`](extensions/daug.ts) | **Synchronized & Active** |
| 状态断言验证器（本文 §5） | [`daug/statecheck.py`](daug/statecheck.py) | **Implemented, Real-Repo Validated** |
| 状态检测回归单测 | [`tests/test_statecheck.py`](tests/test_statecheck.py) | **Passed (15/15)** |
| 论文 B 详细方案基准 | 本文件 | **Canonicalized Draft** |
