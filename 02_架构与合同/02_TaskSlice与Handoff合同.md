---
type: architecture-contract
status: approved
revision: 2
updated: 2026-08-29
---

# TaskSlice 与 Handoff 合同

## TaskSlice 必需字段

- task_slice_id 与 revision；
- objective；
- non_goals；
- authority / user approval；
- exact inputs 与 hashes；
- preconditions；
- allowed read/write paths；
- allowed tools；
- expected outputs；
- promotion plan（交付、入库与后续处置）；
- validation commands；
- stop conditions；
- rollback；
- intended worker；
- handoff target；
- attempt policy。

`promotion_plan` 是 TaskSlice 的一等字段，不得只隐含在产出清单中。凡是可能从 workspace 进入受治理路径的产出，都必须明确：候选位置、目标位置、触发条件、批准指针、实际写入主体、逐文件 SHA 复算、留痕方式和回滚 Gate。Pi worker 的 allowlist 不得因为该计划而获得 canonical 写权限。

## 生命周期

~~~text
proposed
→ ready
→ claimed
→ running
→ submitted
→ accepted
~~~

异常状态：

- blocked；
- failed；
- cancelled；
- rejected；
- superseded。

accepted 只表示任务合同完成，不表示科学结论成立。

## Handoff 规则

消息只传：

- bundle path；
- SHA-256；
- state pointer；
- sender；
- intended receiver。

完整内容进入 HandoffBundle。接收方必须复算 SHA、核对 intended identity 和 TaskSlice revision。

## 任务包与审核包

- Implementation Task Package 与 Validation Review Package 都是对应 HandoffBundle 的载荷/derived view，不是新的 canonical 对象。
- 每个包的字段必须能追溯到 TaskSlice 字段，或追溯到其 exact inputs 引用的冻结合同文件；包不能自行扩大范围或改变权威语义。
- 两个包均使用共同四段骨架：范围、入口与指针、产出清单、门禁。
- Implementation Task Package 可扩展权限与 allowlist、validation commands、停止条件、retry、rollback、promotion plan 和报告格式；Validation Review Package 可扩展独立性、前置条件、盲审顺序、负向测试、判定词表和只读约束。
- 包正文随 HandoffBundle 一次渲染并固定一个 SHA；渲染错误创建新包版本，不修改既有不可变记录。
- 包与冻结合同冲突时以合同为准；模板变更必须经过 G-010，已生成包不因模板更新而改变。

## 幂等

- 一个 TaskSlice 可有多个 attempt；
- 一个 attempt 只能 canonical commit 一次；
- 重发同一 ResultBundle 返回既有结果；
- retry 创建新 attempt，不覆盖旧日志；
- superseded TaskSlice 的未开始 attempt 自动拒绝。

模板：

- [[../templates/TaskSlice]]
- [[../templates/HandoffBundle]]
- [[../templates/ResultBundle]]
