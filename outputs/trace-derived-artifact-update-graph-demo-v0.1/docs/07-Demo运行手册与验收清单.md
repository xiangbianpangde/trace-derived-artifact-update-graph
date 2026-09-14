# 轨迹驱动的动态制品更新图 Demo 运行手册与验收清单

## 目的

本手册定义一个可在五分钟内讲清核心机制、在三十分钟内完成证据复核的 Demo。命令名称是拟议接口，只有在 MVP 实现并通过测试后才能执行。当前文件是运行规范，不是运行记录。

Demo 展示四件事：轨迹如何产生边证据、变化如何触发候选检查、verifier 如何阻止相关度直接变成修改，以及系统如何处理负对照和自强化。

## 演示边界

- 使用本地样例仓库和去敏轨迹。
- 不连接生产仓库、远程文档或真实客户数据。
- 不自动修改源仓库。
- 补丁只写入运行报告或隔离预览目录。
- 所有“通过”结论均绑定本次 run_id 和 manifest。

## 前置条件

| 检查项 | 要求 |
| --- | --- |
| 代码版本 | 绑定到明确 commit SHA |
| 数据库 | 新建或从冻结 fixture 恢复 |
| 样例仓库 | 内容哈希与 manifest 一致 |
| 轨迹文件 | JSON Schema 校验通过 |
| 策略 | `mode: propose_only` |
| 模型 | 明确版本；无写入工具 |
| 网络 | 可选；离线规则场景必须可运行 |
| 输出目录 | 新建且位于允许根目录 |

开始前在屏幕上显示 `policy mode`、仓库哈希和 `run_id`，避免观众把补丁预览理解为已写回。

## 样例材料

```text
fixtures/
├── repo-before/
├── changes/
│   ├── A-interface-change.diff
│   ├── B-local-refactor.diff
│   ├── C-bulk-format.diff
│   └── D-induced-access.jsonl
├── traces/
│   ├── organic-interface-change.jsonl
│   └── assisted-unrelated-read.jsonl
├── labels/
│   └── gold.json
└── manifests/
    └── demo-manifest.json
```

本包中的 `examples/demo_trace.jsonl` 只展示事件格式，不能替代完整 fixture。

## 五分钟演示脚本

### 第一步 展示问题

打开 `src/auth/user_context.ts`、`docs/auth_design.md` 和 `docs/rollout_plan.md`。指出设计文档描述公共字段 `user_id`，而代码差异将其改为 `subject_id`。两者没有 import 关系。

要说明的边界：系统事先不知道文档一定需要修改，只知道它值得检查。

### 第二步 导入轨迹

拟议命令：

```text
daug trace ingest fixtures/traces/organic-interface-change.jsonl
```

报告应显示：

- schema validation 为 pass
- trace completeness 为 complete
- organic 和 recommended 事件数分别列出
- 原始敏感正文未保存
- trace digest 已生成

### 第三步 构建图并解释候选

```text
daug graph build --until 2026-09-14T00:00:00Z
daug candidates rank --change change-interface-001 --top-k 10
```

候选报告至少显示：

| 排名 | 制品 | 总分 | 主要证据 |
| --- | --- | --- | --- |
| 1 | `tests/auth_filter.test.ts` | 示例值 | 静态关系、失败链 |
| 2 | `docs/api_contract.md` | 示例值 | 显式字段引用、历史共变更 |
| 3 | `docs/auth_design.md` | 示例值 | organic trace、语义、任务族 |

界面中不得只显示总分。每个候选必须能展开到 EdgeEvidence。

### 第四步 验证陈旧

```text
daug verify --candidate-set candidate-set-001
```

预期：

- `docs/auth_design.md` 的旧字段陈述为 `STALE`
- 目标行或内容锚点明确
- 证据包含源差异和当前代码版本
- 与该变化无关的 `docs/rollout_plan.md` 为 `NOT_APPLICABLE` 或 `VALID`
- 证据不足的样本保留 `UNCERTAIN`

### 第五步 生成补丁预览

```text
daug patch propose --verification ver-auth-design-001
```

预期补丁只更新受影响的字段描述，包含 expected target hash、patch digest、tests to run 和 rollback material。状态停在 `PATCH_PROPOSED`。

### 第六步 运行负对照

```text
daug candidates rank --change change-refactor-001 --top-k 10
daug verify --candidate-set candidate-set-refactor-001
```

预期：局部变量 rename 的影响类别为 `refactor`；即使 `auth_design.md` 与源文件历史相关，验证器也不生成补丁。

### 第七步 展示自强化控制

导入一次系统推荐后发生的无关读取。候选解释应把该证据列为 `system_recommended`，并显示其权重低于 organic evidence。再次构图后，无关边不能大幅上升。

## 三十分钟技术复核

### 账本检查

- 逐条核对 sequence_no 是否连续。
- 检查每个 edit 是否有 before_hash 和 after_hash。
- 检查 recommended event 是否绑定 recommendation_id。
- 检查 trace_digest 是否与独立复算一致。
- 检查不完整轨迹是否被排除在训练外。

### 图检查

- 选取候选边，回溯到原始 ToolEvent、Git 或静态证据。
- 检查边是否有方向和 change_type。
- 检查大任务惩罚和时间衰减。
- 对比包含和不包含工具轨迹的排名。
- 检查 organic 和 recommended support 是否分开。

### 验证检查

- 用当前目标哈希重新读取目标片段。
- 核对 claim 与源差异是否存在直接逻辑关系。
- 检查模型是否只看到了必要证据。
- 检查模式外输出是否被判为 `UNCERTAIN`。
- 检查验证结果没有被表述为已应用修改。

### 补丁检查

- 目标路径位于允许根目录。
- expected hash 与生成时目标一致。
- 变更范围不超出 affected spans。
- 回滚材料存在。
- 没有 commit、push、PR 或 merge 副作用。

## 验收清单

### 功能验收

- [ ] JSONL 轨迹通过 schema 校验
- [ ] 重复导入保持幂等
- [ ] 事件账本可按 trace 重放
- [ ] 制品和版本哈希可查询
- [ ] 图边可追溯到独立证据
- [ ] 候选输出包含特征分解
- [ ] verifier 输出固定四值状态
- [ ] `STALE` 包含 claim span 和 evidence IDs
- [ ] PatchProposal 绑定目标哈希
- [ ] MVP 不包含真实写回命令

### 安全验收

- [ ] 路径逃逸测试被拒绝
- [ ] 符号链接越界测试被拒绝
- [ ] secret fixture 不出现在持久日志
- [ ] 提示注入 fixture 不触发额外工具调用
- [ ] 受保护制品不能进入自动应用状态
- [ ] 未知 policy value 失败关闭
- [ ] 哈希冲突停止流程
- [ ] 每次重试产生新 attempt_id

### 方法学验收

- [ ] 训练与测试按时间切分
- [ ] 测试提交未参与构图
- [ ] organic 和 assisted 轨迹未混合
- [ ] 大任务未生成完整 pair clique
- [ ] 负对照保留在主报告
- [ ] UNKNOWN 未被强制改标
- [ ] 主结果可由独立脚本复算
- [ ] 报告同时给出样本数、置信区间和成本

### 展示验收

- [ ] 首页清楚显示 `Proposed` 和 `propose_only`
- [ ] 观众能看到 source change、candidate、verification、patch 四个不同对象
- [ ] 总分旁边显示证据来源
- [ ] 补丁预览旁边显示 `not applied`
- [ ] 负对照和失败状态被演示
- [ ] 结束页明确列出未完成的真实宿主、生产和人工验收状态

## 建议输出文件

每次 Demo 运行生成独立目录：

```text
runs/<run_id>/
├── run_manifest.json
├── trace_summary.json
├── graph_snapshot.json
├── candidate_sets.jsonl
├── verifications.jsonl
├── patch_proposals/
├── metrics.json
├── report.html
└── hashes.sha256
```

运行目录不可覆盖。失败重跑创建新的 run_id，并在 manifest 中引用前一次 attempt。

## 预期报告首页

报告首页应直接回答：

- 本次变更是什么
- 哪些制品被召回
- 哪些具体陈述被判为陈旧
- 哪些补丁被提出但未应用
- 哪些证据缺失或不确定
- 当前运行使用的代码、图、模型和策略版本

不得使用“系统已自动维护仓库”等超出事实的描述。

## 常见失败与处理

| 失败 | 处理 |
| --- | --- |
| schema validation failure | 停止导入，修复适配器或 fixture |
| trace incomplete | 允许只读查看，不参与在线学习和主评测 |
| candidate set empty | 保存空结果，检查候选池与变化分类，不扩大权限 |
| verifier timeout | 返回 `UNCERTAIN`，记录成本和超时 |
| evidence conflict | 返回 `UNCERTAIN`，交给人工复核 |
| target hash conflict | 重新读取并创建新 Verification |
| protected artifact hit | 只生成审查任务，不生成自动动作 |
| replay digest mismatch | 停止发布该图和实验结果 |

## 演示完成状态

演示结束时，主持人应逐项宣布实际状态，例如：

```text
Event ingestion: Tested
Offline replay: Tested
Candidate ranking: Tested on demo fixture
Staleness verification: Tested on synthetic fixture
Real Agent host integration: Pending or Interactively verified
Patch application: Not implemented
Human acceptance: Not requested
Production enablement: Not authorized
```

只有实际证据支持的状态才能填写为 Tested 或 Interactively verified。

