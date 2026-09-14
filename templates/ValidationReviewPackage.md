---
type: package-template
template_id: TP-VAL-001
template_version: 2
status: approved
gate_ref: G-010
source_handoff_template: HandoffBundle.md
source_task_contract: ../02_架构与合同/02_TaskSlice与Handoff合同.md
source_shared_contract: ../01_需求与验收/08_共享执行与审核合同.md
source_test_contract: ../01_需求与验收/09_TS001_测试与回滚验收.md
---

# Validation Review Package · Template v2

> 静态模板。只负责把已冻结的 `TS001-VAL` 和审核合同渲染为 HandoffBundle 载荷；不执行脚本、不生成 ID、不直接写文件。信封字段以 [[HandoffBundle]] 为准。

## 渲染后的 HandoffBundle 信封

<!-- 来源：templates/HandoffBundle.md。以下字段必须按既有 HandoffBundle 模板填写；占位符由协调方渲染。 -->

~~~yaml
type: handoff-bundle
handoff_id: "{{handoff_id}}"
status: "{{handoff_status}}"
sender: "{{sender}}"
intended_receiver: "{{intended_receiver}}"
created: "{{created}}"
task_slice_ref: "{{task_slice_ref}}"
attempt: "{{attempt}}"
state_pointer: "{{state_pointer}}"
bundle_sha256: "{{bundle_sha256}}"
expires_at: "{{expires_at}}"
~~~

<!-- 包渲染元数据是载荷元数据，不改变 HandoffBundle 信封字段： -->

~~~yaml
template_ref: "TP-VAL-001@v2"
template_sha256: "{{template_sha256}}"
shared_contract_ref: "{{shared_contract_ref}}"
shared_contract_sha256: "{{shared_contract_sha256}}"
test_contract_ref: "{{test_contract_ref}}"
test_contract_sha256: "{{test_contract_sha256}}"
~~~

### 三层 hash 标注

| 标识 | 占位符 | 来源与规则 |
|---|---|---|
| worker 自报 | `{{worker_reported_sha256}}` | 从 VAL ResultBundle 原样复制；不改写为权威值 |
| 协调方 pre-Harness 复算 | `{{coordinator_pre_harness_sha256}}` | 从协调方复算记录复制；填写时不得由模板重算 |
| Harness 权威复算 | `{{harness_authoritative_sha256}}` | TS-002 后从 Harness 结果复制；TS-001 可填 `not_available_pre_harness` |
| 候选实现 SHA | `{{candidate_sha256}}` | 从冻结 HandoffBundle/候选清单复制；VAL 每次读取前复验 |
| 包 SHA | `{{bundle_sha256}}` | 渲染器在完整载荷固定后计算一次 |
| 模板 SHA | `{{template_sha256}}` | 从被批准的模板文件固定版本计算并记录 |

## 1. 范围

<!-- 来源：TS001-VAL.objective + TS001-VAL.non_goals。填写人：协调方渲染；审核者只读接收。 -->

### 做什么

{{objective}}

### 不做什么

{{non_goals}}

## 2. 入口与指针

<!-- 来源：TS001-VAL.authority_ref、exact_inputs、revision、候选 HandoffBundle 和 CT-001。 -->

### 读取顺序

1. `{{state_pointer}}`
2. `{{shared_contract_ref}}`（SHA：`{{shared_contract_sha256}}`）
3. `{{test_contract_ref}}`（SHA：`{{test_contract_sha256}}`）
4. `{{task_slice_ref}}`（revision：`{{task_slice_revision}}`）
5. 候选 HandoffBundle：`{{candidate_handoff_path}}`（SHA：`{{candidate_handoff_sha256}}`）
6. 候选文件清单：`{{candidate_manifest_path}}`

### 前置条件

{{preconditions}}

VAL 只有在 `TS001-IMPL` 已 `accepted` 且候选 SHA 已冻结后才能进入 `running`。

### 入库边界

<!-- 来源：TaskSlice.promotion_plan + CT-001「TS-001 交付与入库计划」。VAL 只报告审核结果，不执行入库。 -->

- VAL 不负责候选晋升、canonical bootstrap 或 canonical 文件写入；
- `CONFORMANT` 只作为协调方提交用户入库审批的工程结果，不是入库授权；
- 入库与后续缺陷处置按冻结 TaskSlice 的 `promotion_plan` 和 CT-001 执行：`{{promotion_plan}}`。

## 3. 产出清单

<!-- 来源：TS001-VAL.expected_outputs、只读/写入 allowlist、TS-001 测试合同和 ResultBundle。 -->

| 产出 | 允许路径 | 预期状态 | SHA 来源 |
|---|---|---|---|
| 盲审记录 | `{{blind_review_path}}` | 必须存在 | `{{blind_review_sha256}}` |
| 交叉核对记录 | `{{cross_check_path}}` | 必须存在 | `{{cross_check_sha256}}` |
| 审核测试日志 | `{{validation_log_path}}` | 必须存在 | `{{validation_log_sha256}}` |
| VAL ResultBundle | `{{result_bundle_path}}` | `submitted` | `{{result_bundle_sha256}}` |
| 审核报告 | `{{review_report_path}}` | `{{review_report_status}}` | `{{review_report_sha256}}` |

### ResultBundle 约束

- VAL 只能提交复算结果、偏差、缺口、未完成项和证据指针；
- VAL 不修改 IMPL workspace、实现文件、canonical state、`00_入口/00_当前.md` 或 `.obsidian/`；
- 所有候选文件每次读取前重新核对 SHA；漂移即 `INCOMPLETE` + `fail_closed`，退回新 attempt；
- 审核 ResultBundle 不构成批准、人类验收或科学裁决。

## 4. 门禁

<!-- 来源：TS001-VAL.validation_commands、preconditions、stop_conditions、rollback、CT-001 和 TS1-TEST-001。 -->

### 自动验证命令

{{validation_commands}}

每条命令至少记录命令、运行时及版本、输入 SHA、输出/日志 SHA、退出码和起止时间。

### 停止条件

{{stop_conditions}}

### 回滚/退回

{{rollback}}

审核发现候选漂移、SHA 不符或输入缺失时，不能修补候选；必须标记 `INCOMPLETE`，`fail_closed`，并指向新 attempt。

### 批准边界

- 本包只记录 `G-003` 的 VAL TaskSlice / 审核合同批准指针：`{{g003_approval_ref}}`；
- `G-004` 的 per-Run go/no-go 不出现在本包；
- VAL verdict 不改变 TaskSlice、ExperimentSpec、Run 或 Claim 的科学状态。

## Validation 扩展

<!-- 来源：TS001-VAL.preconditions、CT-001 独立性条款和 TS-001 测试合同。 -->

### 独立性与只读边界

- 独立会话：`{{validation_session_id}}`；
- 独立 workspace：`{{validation_workspace}}`；
- 独立缓存根：`{{validation_cache_root}}`；
- 不读取 IMPL 的缓存、scratch 或中间产物；
- 候选读取从 `{{candidate_sha256}}` 开始，每次读取前复验。

### 两段审核顺序

#### 第一段：盲审

<!-- 来源：CT-001 两段式审核条款。此段必须在交叉核对前填写。 -->

- 审核输入：冻结合同、测试合同、候选文件和候选 SHA；
- 不读取：IMPL ResultBundle、开发报告和开发者解释；
- 测试指针：`{{blind_test_pointers}}`；
- 盲审结果：`{{blind_review_result}}`；
- 盲审证据：`{{blind_review_evidence}}`。

#### 第二段：交叉核对

<!-- 来源：CT-001 两段式审核条款。只有第一段完成后才填写。 -->

- 可读取：IMPL ResultBundle、开发报告和执行日志；
- 交叉核对项：`{{cross_check_items}}`；
- 交叉核对结果：`{{cross_check_result}}`；
- 差异清单：`{{discrepancy_list}}`。

### 负向测试

<!-- 来源：TS-001 测试合同。指针必须来自冻结清单，不得临时扩大。 -->

- 权限/引用：`{{negative_permission_tests}}`（TS1-P-*）；
- Handoff/Result：`{{negative_handoff_result_tests}}`（TS1-I-*）；
- 回滚相关：`{{negative_rollback_tests}}`（TS1-R-*）；
- 预期拒绝：`{{expected_rejections}}`；
- 实际证据：`{{negative_test_evidence}}`。

### Verdict 封闭词表

`verdict` 只能取下列值，且不得渲染为 `PASS` 或 `approved`：

| Verdict | 含义 | 明确不等于 |
|---|---|---|
| `CONFORMANT` | 按冻结 revision 与候选 SHA 完成盲审和交叉核对，未发现偏差 | `approved`、用户人类验收、科学支持 |
| `DEVIATIONS_FOUND` | 发现偏差、绕过或缺口，并附清单与复现指针 | 自动修复、科学批准或否定 |
| `INCOMPLETE` | 审核无法完成，例如候选漂移、SHA 不符或输入缺失 | 通过 |
| `OUT_OF_SCOPE` | 发现超出本 TaskSlice 范围的事项，转协调方或用户另行处置 | 本切片的失败判定或批准 |

最终 verdict：`{{verdict}}`

### INCOMPLETE 处理路径

1. 停止继续读取漂移候选；
2. 保留当前审核 workspace、命令和证据；
3. 提交 `INCOMPLETE` 的 VAL ResultBundle；
4. 由协调方记录 `fail_closed` 和候选漂移原因；
5. 退回 `TS001-IMPL` 新 attempt；
6. 新候选 SHA 冻结后，创建新的 VAL attempt；不覆盖旧审核记录。

## 占位符来源表

| 占位符类别 | 代表字段 | 来源 | 填写人 | 规则 |
|---|---|---|---|---|
| 信封 | `handoff_id`、`sender`、`intended_receiver`、`state_pointer` | `templates/HandoffBundle.md` + Handoff 记录 | 协调方 | 不在本模板生成或改义 |
| VAL TaskSlice | `objective`、`non_goals`、`preconditions`、`rollback`、`promotion_plan` | 冻结 TS001-VAL revision | 协调方 | 必须保留合同指针 |
| 候选 | `candidate_sha256`、候选文件清单 | IMPL HandoffBundle + 协调方复算 | 协调方/VAL复验 | 从冻结来源复制；每次读取复验 |
| 测试 | `test_contract_ref`、TS1-P/I/R 指针 | TS-001 测试合同 | 协调方 | 不得临时扩大 |
| Verdict | `verdict` | CT-001 封闭词表 | VAL填写 | 只能取四个工程域词 |
| 渲染 | `template_sha256`、`bundle_sha256` | 模板文件/完整载荷 | 渲染器 | 固定后生成一次 |

## 渲染规则

1. 先复算冻结合同、候选清单和测试合同的 SHA，再复制到占位符；
2. 由协调方填写包，VAL 只读接收；
3. 生成包必须记录模板版本和模板 SHA；
4. VAL 的盲审段必须先于交叉核对段；
5. 包与合同冲突时以合同为准；渲染错误创建新包版本；
6. 模板不得执行脚本、生成 ID、创建目录、移动文件或直接写入库。
