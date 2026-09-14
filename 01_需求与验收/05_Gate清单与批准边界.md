---
type: gate-contract
status: approved
question_id: Q-004
updated: 2026-08-29
---

# Q-004 Gate 清单与批准边界

本文件只冻结“哪些动作必须经过人工 Gate”。批准由谁执行、批准如何落盘、是否允许批量批准，暂不在本题决定。

状态说明：Q-004 的决策内容已被用户接受，P0 整体已于 `P0-20260829-001` 批准；本文件当前为 `status: approved`。后续语义变化必须创建新 revision 并重新走相应 Gate。

## Gate 的两层含义

### 自动 Gate

Harness 在任何 canonical transaction 前必须自动检查：

- schema；
- entity identity 与 version；
- reference 可解析性；
- TaskSlice allowlist；
- artifact hash；
- required invariants；
- transaction 一致性。

自动检查通过不等于人工审查完成。自动 Gate 拒绝时，canonical transaction 必须零写入，不能提交对应的成功 Event；拒绝原因返回调用方。人工批准也不能绕过自动 Gate。

### 人工 Gate

人工 Gate 是对计划、权限、科学含义或异常处置的明确授权。人工 Gate 通过后，仍必须再次通过自动 Gate 才能提交。

## P0 人工 Gate 清单

| Gate ID | 类别 | 动作 | P0 要求 | 结果边界 |
|---|---|---|---|---|
| G-001 | 科学 Gate | 创建或语义修改定义对象 | 必须人工批准 | 创建新 revision；不得原地覆盖历史定义 |
| G-002 | 科学 Gate | 冻结或修订 Protocol / `ExperimentSpec` | 必须人工批准 | 冻结后不得改变已绑定 Run 的版本 |
| G-003 | 产品/工程 Gate | 批准 `TaskSlice` | 必须人工批准 | 只批准计划、输入、范围、allowlist、输出和停止条件 |
| G-004 | 产品/工程 Gate | 启动一次 fixture Run | P0 每次执行都需 go/no-go | TaskSlice 批准不等于本次 Run 已启动 |
| G-005 | 科学 Gate | 冻结 `EvidenceSnapshot` | 必须人工/领域批准 | 固定 included、considered、excluded evidence 及其版本 |
| G-006 | 科学 Gate | 接受或语义修订 `EvidenceCard` | 必须人工/领域批准 | 更正创建新版本，并传播 stale/needs_review |
| G-007 | 科学 Gate | 接受、撤回或标记 Claim | 必须人工/领域批准 | 不得由 Text Agent 自我批准 |
| G-008 | 科学 Gate | 将 fixture/synthetic/public dataset 结果升级为非临床科学或方法表述 | 必须人工批准 | 仅限工程、流程或非临床范围；必须保留 data_class、scope 与 limitations |
| G-009 | 产品/工程 Gate | 修改权限、allowlist、工具能力或插件写入面 | 必须人工批准 | 先更新合同和负向测试，再改变运行策略 |
| G-010 | 产品/工程 Gate | 修改模板语义 | 必须人工批准 | 模板视为合同入口；已有记录不得被模板变更重写 |
| G-011 | 产品/工程 Gate | 改变阶段、数据边界或 fixture/test contract | 必须人工批准 | P0→P1、启动 formal experiment、解除 P0–P5 真实数据禁令、fixture 实质性变更都属于新 Gate |
| G-012 | 产品/工程 Gate | 库结构级变更 | 必须人工批准 | 新增/重命名顶层目录、平行 current/LOG/研究树、整棵子树迁移均需 Gate |
| G-013 | 产品/工程 Gate | 异常与恢复处置 | 必须人工批准 | Gate 拒绝后的重试/放弃/升级、`needs_reconcile` 处置、重跑 completed Run 均需明确语义 |
| G-014 | 产品/工程 Gate | canonical 文件迁移、删除或恢复 | 必须人工批准 | 必须核对 identity、version、hash、引用和回滚方案 |

## TaskSlice 批准与 fixture Run 启动

两者是两个不同的 Gate：

```text
TaskSlice 批准
  = 批准计划、输入、范围、allowlist、输出和停止条件

fixture Run 启动
  = 针对本次 attempt 的 go/no-go
```

P0 中，两个 Gate 都必须通过。`启动 fixture Run | human gate until policy approved` 的到期语义是：P0 内没有自动到期；在未来 P1，只有新的阶段/策略 Gate 明确批准后，才可以改为“TaskSlice 批准即授权 allowlist 内执行”。P1 不会自动解除该 Gate。

## INV-013 的绝对边界

fixture/synthetic 证据产生临床有效性或临床效果 Claim 是 **deny**，不是待批准的 Gate：

- 任何人工批准都不能解锁该动作；
- 自动 Gate 和人工 Gate 均必须拒绝；
- 允许进入人工 Gate 的，只能是非临床的工程、流程或方法表述，例如“闭环在指定 fixture 场景中完成”。

这与 INV-013 是同一条绝对禁止，不得把“human gate”解释为可授权例外。

## 不需要人工 Gate 的动作

| 动作 | 类别 | 约束 |
|---|---|---|
| 读取项目文件 | 产品/工程 | 仍受敏感数据和路径策略限制 |
| 在 active TaskSlice allowlist 内写 workspace | 产品/工程 | 不能写 canonical |
| 创建或修改 proposal/draft | 产品/工程 | 只能进入 `09_提案与草稿/`，状态保持 proposed |
| 生成或重建 derived index / materialized view | 产品/工程 | 可删除重建，不能成为事实源 |
| 追加 `07_运行记录/LOG.md` | 产品/工程 | 只能通过 append-only 接口，不能修改历史行或冒充批准 |
| Harness 复算 hash、生成 Manifest 和提交经过自动 Gate 的运行记录 | 产品/工程 | “经过检查”只指 schema/reference/invariant 等自动检查，不指人工审查 |
| 主协调 Agent 更新 `00_入口/00_当前.md` 的导航内容 | 产品/工程 | 不得覆盖 canonical state 或宣称科学批准 |

## 未覆盖动作的默认原则

两个清单都没有明确列出的动作，默认进入人工 Gate，并在动作被定义、分类和测试前保持 fail closed。该默认原则不替代 Q-006 对错误处理语义的进一步细化。

## 待后续决定

以下内容不在 Q-004 冻结：

- 哪一个具体人或角色拥有批准权；
- 批准记录使用何种字段或 Approval Event；
- 是否允许批量批准；
- 批准是否需要二次确认或领域签名。
