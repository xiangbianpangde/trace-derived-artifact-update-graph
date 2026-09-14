# 轨迹驱动的动态制品更新图 Demo 技术方案包

版本：v0.1

状态：方案草案

更新日期：2026-09-14

## 结论

本方案建议先实现一个默认只读、只提出补丁、不自动写回的 Demo。系统从 Agent 的 `read`、`search`、`edit`、`write`、`test` 等工具事件中提取行为信号，与 Git 共变更、静态依赖、显式引用和语义相似度合并，建立有方向、带变化类型的 Artifact Update Graph。文件发生变化后，图只负责召回可能受影响的制品；独立的 staleness verifier 再判断具体陈述是否失效。只有验证成立、策略允许且目标版本未变化时，系统才生成最小补丁。

MVP 的目标是验证两个问题：工具轨迹能否提高受影响制品的召回率，以及独立的陈旧验证能否降低错误更新。MVP 不证明系统可以安全自治，也不授权生产写回。

## 目录

```text
trace-derived-artifact-update-graph-demo-v0.1/
├── README.md
├── Trace-Derived-Artifact-Update-Graph-Demo-技术方案-v0.1.md
├── docs/
│   ├── 01-总体技术方案.md
│   ├── 02-系统架构与数据模型.md
│   ├── 03-MVP与Demo实施计划.md
│   ├── 04-评测与消融实验方案.md
│   ├── 05-风险与治理.md
│   ├── 06-后续研发与论文规划.md
│   └── 07-Demo运行手册与验收清单.md
├── assets/
│   ├── system-architecture.svg
│   ├── system-architecture.png
│   ├── update-lifecycle.svg
│   ├── update-lifecycle.png
│   ├── data-model.svg
│   └── data-model.png
├── schemas/
│   ├── sqlite_schema.sql
│   └── tool_event.schema.json
├── examples/
│   ├── demo_trace.jsonl
│   └── policy.example.yaml
├── references/
│   └── 参考资料.md
└── MANIFEST.sha256
```

本包只交付 Markdown 及其机器可读附件，不包含 Word 文件。

## 阅读路径

| 角色 | 建议顺序 | 需要作出的决定 |
| --- | --- | --- |
| 技术负责人 | 01 → 02 → 03 → 05 | 是否按默认只读边界启动 MVP |
| 实施人员 | 02 → 03 → 07 → schemas | 数据契约、模块边界和验收测试是否足够明确 |
| 研究人员 | 01 → 04 → 06 → references | 研究问题、对照组、标签和泄漏控制是否成立 |
| 安全与治理评审 | 05 → 02 → 07 | 日志最小化、写回闸门和审计证据是否可接受 |

## 文件状态词

本包严格区分以下状态。后一个状态不能从前一个状态自动推出。

| 状态 | 含义 |
| --- | --- |
| Proposed | 已写入方案，尚未实现 |
| Implemented | 已实现，但尚未通过约定测试 |
| Tested | 已通过明确列出的自动化测试 |
| Interactively verified | 已用真实客户端或界面完成交互验证 |
| Human accepted | 人工评审已明确接受 |
| Canonicalized | 已由有权限的人或流程写入正式来源 |

当前文档包整体状态为 `Proposed`。文中的精度、延迟、成本和样本量均为建议目标或实验设计，不是已取得的结果。

## 核心边界

- 相关性分数只触发检查，不能直接触发修改。
- `STALE` 是带证据的审查判断，不等于目标文件可被自动改写。
- Agent 自发访问和系统推荐后访问必须分别记录，避免推荐行为强化自己的边权。
- 每次补丁都绑定目标文件的内容哈希；哈希不一致时停止写回并重新验证。
- MVP 默认运行到 `PATCH_PROPOSED`，不进入 `APPLIED`。
- 安全策略、权限配置、部署配置、法律或合规文本、临床或科研结论等受保护制品不允许自动写回。

## Demo 最短路径

1. 向样例仓库注入一条接口变化，同时保留一份仍使用旧字段名的设计文档。
2. 导入 Agent 工具轨迹和仓库静态证据。
3. 构建或增量更新 Artifact Update Graph。
4. 以本次代码差异为输入召回 Top K 候选文件。
5. 对候选文件中的可核验陈述执行 staleness verification。
6. 生成带证据、目标哈希和回滚信息的最小补丁提案。
7. 运行负对照：仅修改局部变量名，确认系统不会把相关文档标为必须更新。

完整演示步骤见 [Demo 运行手册与验收清单](docs/07-Demo运行手册与验收清单.md)。

## 建议的启动决定

批准四周、单仓库、离线回放、只读采集和补丁提案模式的 MVP。第一周先冻结事件契约、状态机、标签规则和验收测试；在候选召回及负对照达到预设门槛之前，不接入真实自动写回。
