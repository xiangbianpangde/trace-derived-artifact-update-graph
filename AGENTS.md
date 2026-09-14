# AGENTS.md

本文件适用于整个 DAUG-Demo 工程目录。

## 每次会话启动必须执行

1. 读取 `README.md`。
2. 读取 `00_入口/00_当前.md`（全库唯一权威物理当前状态）。
3. 读取根目录 `HANDOFF.md`（全库唯一当前全局交接）。
4. 读取 `06_任务与交接/active/` 中的在轨活跃目标任务切片。
5. 修改文件前检查同目录现有内容与活动引用链接。

## 当前阶段

当前为 P0 初始化基线阶段。除非用户另行明确批准：
- 只完善需求、边界、合同、测试与实施计划；
- 不在主分支编写未经批准的生产实现；
- 不擅自引入未经登记的外部依赖或真实生产/敏感数据；
- 不随意变更既有技术架构基线。

## 四方权力边界体系

- **用户 (Human Owner)**: 产品/科研目标、实质授权、人类验收和业务/科学边界的最终负责人。
- **主协调 Agent (Coordinator)**: 拆任务切片、渲染派发交接包、独立复算 SHA-256、整合证据、暴露待决问题；**严禁自我批准**！
- **实现 Agent (Implementation Worker - IMPL)**: 严格按已冻结的任务包在允许路径白名单内实现；只能写自己的 attempt workspace，产出候选版本；**严禁直接写入 canonical 生产目录**。
- **审核 Agent (Validation Auditor - VAL)**: 独立责任视角，只读冻结合同与候选版本，在独立 workspace 执行盲审与交叉核对；只输出封闭工程判定，**严禁替代人类验收**。

## 单事实源准则

- **全库唯一当前**：`00_入口/00_当前.md`。
- **全库唯一过程日志**：`07_运行记录/LOG.md`（纯追加 append-only，严禁篡改或重排历史行，更正用 `CORRECTION`）。
- **全库唯一当前交接**：根目录 `HANDOFF.md`；历史交接归档于 `06_任务与交接/handoffs/`。
- **暂存隔离原则**：未经 Gate 批准的提案与草稿统一入 `09_提案与草稿/`，严禁未经批准直接落入 canonical 生产目录。
- **不可变凭据保留**：HandoffBundle 与 ResultBundle 归档于 `06_任务与交接/records/<task_slice_id>/<attempt_id>/`，被拒绝的尝试亦必须永久保留留痕。

## 六级状态词分离协议

必须严格区分以下六级状态，绝对不可相互混淆或替代：
- `proposed`: 已提出，未批准。
- `approved`: 用户或相应 Gate 已批准进入下一阶段。
- `implemented`: 候选代码或产物已生成于 workspace。
- `tested`: 自动化机器测试已全部通过。
- `human-accepted`: 用户已完成真实交互、功能审查或场景使用验收。
- `scientifically-supported` (或 `verified-in-prod`): 结论已获确凿证据链充分支撑。

**警示**：工具返回成功 (exit code 0)、文件存在或测试通过，**绝对不等于**用户验收或业务结论成立！

## 审核判定封闭词表 (Validation Verdicts)

审核 Worker 的 ResultBundle 判定必须且仅限以下四词：
- `CONFORMANT`: 按冻结合同与候选 SHA 完成复算与测试，未发现工程偏差。
- `DEVIATIONS_FOUND`: 发现偏差、绕过或缺口，并附清单与复现依据。
- `INCOMPLETE`: 审核无法完成（如候选 SHA 漂移、环境缺失或输入不完整）。
- `OUT_OF_SCOPE`: 发现超出当前任务切片范围的事项，转协调方或用户处置。

## 沙箱与两阶段入库规范 (Promotion Plan)

- 库根只读 + 白名单写入面。
- Worker 只能写自己的 `03_实现/workspaces/<task_slice_id>/<attempt_id>/` 和受控 ResultBundle 提交通道。
- 严禁在工程中保存任何明文密钥、API Token、密码或未经脱敏的真实敏感数据。
- 候选成果必须先在 workspace 交付，经协调方复算、审核方验证出具 `CONFORMANT`，并由用户下发明确入库指令后，方可由协调方原子执行 Canonical Bootstrap 晋升入库。

## 错误处置与 Fail-Closed 原则

- **提交前违规 / 校验失败**：立即触发 `fail_closed`，全库 canonical 零写入，并在 `07_运行记录/LOG.md` 追加拒绝留痕。
- **提交后状态撕裂**：触发 `needs_reconcile`，阻断下游依赖并等待人工介入。
- **上游版本变更**：标记 `stale/needs_review`，不自动否定。
- **可恢复失败**：通过人工发起新 attempt 进行 `retry`，保留旧历史。

## 极小化交接消息协议

交接交互消息只传递五元组：
1. 文件路径 (`bundle_path`)；
2. 校验哈希 (`SHA-256`)；
3. 状态指针 (`state_pointer`)；
4. 发送方 (`sender`)；
5. 接收方 (`intended_receiver`)。

完整任务、结果和说明必须完全落入 `TaskSlice`、`ResultBundle` 或 `HandoffBundle` 物理文件中。
