---
type: package-template
template_id: TP-IMPL-001
template_version: 2
status: approved
gate_ref: G-010
source_handoff_template: HandoffBundle.md
source_task_contract: ../02_架构与合同/02_TaskSlice与Handoff合同.md
source_shared_contract: ../01_需求与验收/08_共享执行与审核合同.md
---

# Implementation Task Package · Template v2

> 静态模板。只负责把已冻结的 `TaskSlice` 和合同字段渲染为 HandoffBundle 载荷；不执行脚本、不生成 ID、不直接写文件。信封字段以 [[HandoffBundle]] 为准，本文件不重新定义其语义。

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
template_ref: "TP-IMPL-001@v2"
template_sha256: "{{template_sha256}}"
shared_contract_ref: "{{shared_contract_ref}}"
shared_contract_sha256: "{{shared_contract_sha256}}"
~~~

### 三层 hash 标注

| 标识 | 占位符 | 来源与规则 |
|---|---|---|
| worker 自报 | `{{worker_reported_sha256}}` | 从 IMPL ResultBundle 原样复制；协调方不得把它改写为权威值 |
| 协调方 pre-Harness 复算 | `{{coordinator_pre_harness_sha256}}` | 从协调方复算记录复制；填写时不得用模板逻辑重算 |
| Harness 权威复算 | `{{harness_authoritative_sha256}}` | TS-002 后从 Harness 结果复制；TS-001 可填 `not_available_pre_harness` |
| 包 SHA | `{{bundle_sha256}}` | 渲染器在完整载荷固定后计算一次；不是 worker 自报值 |
| 模板 SHA | `{{template_sha256}}` | 从被批准的模板文件固定版本计算并记录 |

## 1. 范围

<!-- 来源：TaskSlice.objective + TaskSlice.non_goals。填写人：协调方渲染；worker 只读接收。 -->

### 做什么

{{objective}}

### 不做什么

{{non_goals}}

## 2. 入口与指针

<!-- 来源：TaskSlice.authority_ref、exact_inputs、TaskSlice revision、HandoffBundle 信封和 CT-001。填写人：协调方。 -->

### 读取顺序

1. `{{state_pointer}}`
2. `{{shared_contract_ref}}`（SHA：`{{shared_contract_sha256}}`）
3. `{{task_slice_ref}}`（revision：`{{task_slice_revision}}`）
4. `{{exact_inputs_pointer}}`
5. `{{acceptance_pointer}}`

### 权威与版本

| 项目 | 值 |
|---|---|
| authority / user approval | `{{authority_ref}}` |
| TaskSlice revision | `{{task_slice_ref}}` |
| shared contract | `{{shared_contract_ref}}` / `{{shared_contract_sha256}}` |
| attempt | `{{attempt}}` |
| candidate status | `{{candidate_status}}` |

## 3. 产出清单

<!-- 来源：TaskSlice.expected_outputs、allowed paths、ResultBundle 合同。填写人：协调方；路径和 SHA 从冻结来源复制。 -->

| 产出 | 允许路径 | 预期状态 | SHA 来源 |
|---|---|---|---|
| 候选实现/测试 | `{{impl_workspace}}` | `{{candidate_status}}` | `{{candidate_sha256}}` |
| 执行记录 | `{{execution_log_path}}` | 必须存在 | `{{execution_log_sha256}}` |
| 开发 ResultBundle | `{{result_bundle_path}}` | `submitted` | `{{result_bundle_sha256}}` |
| 其他合同产物 | `{{other_outputs}}` | `{{other_outputs_status}}` | 从冻结清单复制 |

### ResultBundle 提交约束

- worker 只能提交候选 path、文件清单、执行记录和自报 hash；
- worker 不得直接写 canonical state、Research Event、Manifest、`00_入口/00_当前.md` 或对方 workspace；
- `{{candidate_sha256}}` 等输入/候选 SHA 从冻结来源复制，填写时不得重算或修改；
- 任何未列出的产出都视为越界，停止并报告。

### 交付 / 入库计划

<!-- 来源：TaskSlice.promotion_plan + CT-001「TS-001 交付与入库计划」。填写人：协调方；worker 不因本段获得 canonical 写权限。 -->

{{promotion_plan}}

## 4. 门禁

<!-- 来源：TaskSlice.validation_commands、TaskSlice.stop_conditions、TaskSlice.preconditions、TaskSlice.rollback 和 CT-001。填写人：协调方。 -->

### 自动验证命令

{{validation_commands}}

每条命令都必须记录命令、运行时及版本、输入 SHA、输出/日志 SHA、退出码和起止时间。

### 进入条件

{{preconditions}}

### 停止条件

{{stop_conditions}}

### 回滚

{{rollback}}

### 批准边界

- 本包只记录 `G-003` 的 TaskSlice / 合同批准指针：`{{g003_approval_ref}}`；
- `G-004` 的 per-Run go/no-go 不属于本包，不得由本包状态推断执行授权；
- `CONFORMANT`、`PASS-ENGINEERING` 或包已渲染均不等于用户人类验收或科学支持。

## Implementation 扩展

<!-- 来源：TaskSlice.allowed_read_paths / allowed_write_paths / allowed_tools、CT-001 沙箱条款。 -->

### 权限与 allowlist

#### 可读

{{allowed_read_paths}}

#### 可写

{{allowed_write_paths}}

其中可写面只能是本 attempt workspace 与受控 ResultBundle 提交通道；库根其他位置只读。

### 工具

{{allowed_tools}}

allowlist 不包含网络、下载或凭据读取工具。环境层由用户配置离线/无凭据运行；模板不宣称已实现技术性网络沙箱。

### Retry 与交付报告

- retry 只能由人工发起，并创建新的 `attempt_id`；旧 workspace、日志和 ResultBundle 不覆盖；
- 报告必须区分：已写入、已运行、测试通过、外部验证、用户人类验收和科学支持；
- 开发者只能报告事实和未验证项，不得自我宣布审核通过。

## 占位符来源表

| 占位符类别 | 代表字段 | 来源 | 填写人 | 规则 |
|---|---|---|---|---|
| 信封 | `handoff_id`、`sender`、`intended_receiver`、`state_pointer` | `templates/HandoffBundle.md` + Handoff 记录 | 协调方 | 不在本模板生成或改义 |
| TaskSlice | `objective`、`non_goals`、`preconditions`、`rollback`、`promotion_plan`、allowlist | 冻结 TaskSlice revision | 协调方 | 必须保留来源指针 |
| 合同 | `shared_contract_ref`、`shared_contract_sha256` | CT-001 | 协调方 | 从冻结来源复制 |
| 候选 | `candidate_sha256`、文件清单 | IMPL ResultBundle + 协调方复算记录 | 协调方 | worker 自报值不具权威性 |
| 验收 | `validation_commands`、`acceptance_pointer` | TS-001 测试合同 | 协调方 | 不得加入未批准测试 |
| 渲染 | `template_sha256`、`bundle_sha256` | 模板文件/完整渲染载荷 | 渲染器 | 固定后生成一次 |

## 渲染规则

1. 先复算所有冻结输入文件的 SHA，再复制到占位符；
2. 由协调方填写内容，worker 只读接收；
3. 渲染完成后计算模板 SHA、包 SHA，并把模板版本与 SHA 写入生成包；
4. 包与冻结合同冲突时以合同为准；
5. 渲染错误创建新包版本，不修改已生成包；
6. 模板本身不得执行脚本、生成 ID、创建目录、移动文件或直接写入库。
