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

## 3. 人机协同辅助部署 (P2 Deployment) 架构

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

## 4. 评测协议与实验设计 (P2 Evaluation Protocol)

1. **接受率 (Acceptance Rate, AR)**：
   $$\text{AR} = \frac{\text{Accepted Patches}}{\text{Proposed Patches}}$$
   目标：在真实开发环境下达到 $\text{AR} \ge 80\%$。
2. **审查耗时节约 (Triage Time Reduction)**：
   对比人类手动排查各级关联文档所需时间与基于 `daug review` 分栏界面的确认耗时，目标降低 $\ge 70\%$ 的排查时间。
3. **零破坏写入保证 (Zero Silent Drifts)**：
   在 CAS 保护下，任何外部修改或并发冲突的未授权写回发生率为严格的 **0.0%**。

---

## 5. 阶段交付物矩阵

| 交付模块 | 对应路径 | 交付状态 |
|---|---|---|
| 交互式 Web 审查服务器 | [`daug/server.py`](daug/server.py) | **Implemented & Tested** |
| CLI `daug review` 命令 | [`daug/cli.py`](daug/cli.py) | **Implemented & Ready** |
| Web 服务自动化单测 | [`tests/test_review_server.py`](tests/test_review_server.py) | **Passed (100%)** |
| Pi Agent `/daug review` 扩展 | [`extensions/daug.ts`](extensions/daug.ts) | **Synchronized & Active** |
| 论文 B 详细方案基准 | 本文件 (`reports/03_论文B规划...md`) | **Canonicalized Draft** |
