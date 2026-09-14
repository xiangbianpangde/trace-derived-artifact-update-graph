---
type: error-disposition-contract
status: approved
question_id: Q-006
updated: 2026-08-29
---

# Q-006 错误处置与 fail closed

用户已接受本文件的错误处置映射。P0 整体已于 `P0-20260829-001` 批准，本文件当前为 `status: approved`；后续语义变化须创建新 revision。

## 四档处置

| 处置 | 判别标准 | 系统行为 | 是否属于科学否定 |
|---|---|---|---|
| `fail_closed` | 提交前发现违规，或自动 Gate 不通过 | 零 canonical 写入；返回原因；追加拒绝记录；不得提交成功 Event | 否 |
| `needs_reconcile` | 已提交状态事后发现不一致、不可信或无法证明完整 | 隔离受影响状态；阻止后续依赖；进入 G-013 人工处置；不得静默修复 | 否 |
| `stale/needs_review` | 上游 revision 传播，不是系统违规 | 标记下游对象，等待人工复核；不自动判 false | 否 |
| `retry` | 可恢复的执行失败，且没有权限/合同违规 | 只能由人发起新 attempt；保留旧 attempt 与 workspace；不覆盖历史 | 否 |

`fail_closed` 的“零写入”特指零 canonical mutation 和零成功 Event。拒绝审计行通过唯一的 append-only `07_运行记录/LOG.md` 留痕，但不构成 canonical commit。

## 错误 × 处置映射

| 错误 ID | 错误类别 | 检测点 | 处置 | 恢复路径 | 负向测试 |
|---|---|---|---|---|---|
| E-001 | `ExperimentSpec` 缺失、未批准、版本不精确或已失效 | preflight reference/version Gate；INV-004 | `fail_closed` | 补齐精确版本并重新提交；冻结或修订走 G-002 | F-001、F-002 |
| E-002 | 数据缺少/使用未知 `data_class`、provenance、版本或 hash | data boundary check；INV-016 | `fail_closed` | 先登记或修正数据；需人工确认时走 Q-005/G-011 | F-021、F-022、F-024 |
| E-003 | artifact 缺失、不可解析或 hash 不匹配 | artifact Gate；INV-005 | `fail_closed` | 重新生成或登记新 artifact；不得伪造 hash | F-008 |
| E-004 | worker/Agent 越过 TaskSlice allowlist 或写入未授权路径 | workspace Hook；INV-007 | `fail_closed` | 停止当前请求，修正 TaskSlice 或权限合同；必要时走 G-009 | F-009 |
| E-005 | 提交前直接覆盖 canonical、completed Run 或 immutable record | Mutation Gateway；INV-001、INV-009 | `fail_closed` | 通过新 revision、supersedes 或 Correction Event 表达更正 | F-004、F-037 |
| E-006 | 重复 entity ID、版本冲突或 immutable record 冲突 | identity/version Gate；INV-002 | `fail_closed` | 使用新 identity 或新 revision；不得复用历史 ID | F-003、F-004 |
| E-007 | 提交前无法形成单次原子事务 | transaction prepare；INV-003、INV-012 | `fail_closed` | 零 canonical 写入；修复事务后重新提交；提交状态不确定时转 E-008 | F-006 |
| E-008 | 提交后出现 record/event 半提交或关键 Hook 失败 | commit readback、Hook、Reconciler | `needs_reconcile` | 隔离状态，阻止依赖，按 G-013 决定恢复；不得继续写下游 | F-007、F-031 |
| E-009 | 事后发现历史 immutable record 或 Event hash 被篡改 | chain/hash Reconciler；INV-001 | `needs_reconcile` | 生成安全/完整性事件，保留现场，按 G-013/G-014 人工处置 | F-018 |
| E-010 | Run/Evidence 试图引用真实医疗数据 | data boundary、INV-016、R-007 | `fail_closed` | 拒绝引用；不得把人工批准当作解锁方式 | F-015 |
| E-011 | 真实医疗数据文件本体已经被手工放入库内 | 文件扫描/人工发现 | `needs_reconcile` | 标记并升级 G-014；不得自动删除或复制敏感内容 | F-035 |
| E-012 | 任何数据类别试图产生临床有效性或临床效果 Claim | Claim Gate；INV-013 | `fail_closed` 且不可 Gate 解锁 | 保留拒绝记录；只能改写为合规的非临床表述 | F-036 |
| E-013 | 必须人工批准的动作缺少有效 Gate | Gate registry；G-001～G-014 | `fail_closed` | 退回 proposal，补齐对应 Gate；P0 不自动推断批准 | F-032 |
| E-014 | actor、权限主体、目标对象或允许路径无法确定 | permission/identity check | `fail_closed` | 暂停并要求澄清主体和范围；必要时走 G-009 | F-033 |
| E-015 | Claim、Evidence、Run 等引用无法解析 | reference check；INV-005/006 | `fail_closed` | 修正精确引用或创建新 revision；不使用 `latest` 猜测 | F-026 |
| E-016 | `expected_version` 不匹配或陈旧写入 | transaction compare-and-check | `fail_closed` | 重新读取当前版本并生成新 mutation request；不得强制覆盖 | F-027 |
| E-017 | canonical record 不符合已注册 schema | schema Gate | `fail_closed` | 修正 proposal 或先经合同 Gate 更新 schema | F-028 |
| E-018 | required integrity rule、schema 或 Gate 配置缺失 | startup/preflight integrity check；INV-012 | `fail_closed` | 停止相关能力，恢复规则并通过 Validation Agent 检查 | F-029 |
| E-019 | worker 崩溃、进程中断或其他可恢复执行失败，且无违规证据 | execution supervisor | `retry` | P0 只能人工发起新 attempt；保留旧 workspace、日志和 ResultBundle | F-030 |
| E-020 | 上游定义、Spec 或 Evidence revision 导致下游受影响 | revision propagation；INV-010 | `stale/needs_review` | 标记受影响对象，人工复核；不自动判定 Claim 为 false | F-011、A-011 |
| E-021 | `fail_closed` 已发生但拒绝记录无法追加或内容不完整 | refusal-log postcondition | `needs_reconcile` | 阻止后续受影响请求，修复审计写入，按 G-013 处置 | F-034 |

## 两个关键分界

### 原子事务失败

必须按发生时间点区分：

```text
提交前无法形成事务
  → fail_closed
  → 零 canonical 写入

提交后发现半提交或 Hook 失败
  → needs_reconcile
  → 隔离状态，禁止下游继续依赖
```

不能用“回滚或恢复”一句话覆盖这两个状态，因为前者没有 canonical 状态需要恢复，后者必须保留现场并由人决定恢复语义。

### immutable record 与真实数据文件

```text
提交前试图改 immutable record
  → fail_closed

事后 hash 发现 immutable record 被篡改
  → needs_reconcile + 完整性/安全事件

Run/Evidence 引用真实医疗数据
  → fail_closed

真实医疗数据文件本体已存在
  → 标记 + G-014 人工处置，不自动删除
```

## 拒绝必须留痕

每次 `fail_closed` 都必须通过 Harness 向唯一 `07_运行记录/LOG.md` 追加一条拒绝记录，至少包含：

- `rejection_id`；
- `request_id`；
- `actor`；
- `target`；
- `error_id`；
- 拒绝原因；
- 时间；
- 输入与目标版本/hash 摘要。

拒绝记录本身不是 canonical mutation，不得提交成功 Event。若拒绝记录无法写入或缺字段，触发 E-021，后续相关请求保持 fail closed。

## P0 retry 规则

- 系统可以建议 retry，但不能自动重跑；
- P0 所有 retry 必须由人发起；
- retry 必须创建新的 `attempt_id`；
- 旧 attempt、workspace、Execution Log 和 ResultBundle 保留；
- completed Run 不重跑覆盖，只能创建新 attempt 并进入 G-013 处置；
- schema、权限、数据边界、版本和 Gate 违规不能伪装成 retryable execution failure。

## 默认原则

本文件和非 Gate 清单未明确覆盖的错误，默认按 `fail_closed` 处理；只有在确认属于事后不一致、上游传播或无违规的可恢复执行失败后，才可分别转为 `needs_reconcile`、`stale/needs_review` 或人工发起的 `retry`。

## 相关合同

- Gate 分类与人工批准：[[05_Gate清单与批准边界]]；
- 数据分类与 INV-016：[[06_数据边界]]；
- 可执行不变量：`02_架构与合同/04_可执行不变量.md`；
- 验收矩阵：[[03_验收矩阵]]；
- 失败场景：[[04_失败场景]]。
