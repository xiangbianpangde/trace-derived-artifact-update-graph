# DAUG: 轨迹驱动的动态制品更新图系统 (Trace-Derived Artifact Update Graph Demo)

> **模式声明**：本系统运行于 `propose_only` 只读提案模式。状态为 `Proposed` / `Tested`。系统生成带证据与目标预期哈希的最小补丁提案（Unified Diff），绝无生产写回。

---

## 1. 项目简介

在大模型长程编程（Long-horizon Agentic Coding）场景下，底层代码发生重构时，上游设计文档、API 契约或配置文件往往缺乏显式 `import` 引用，容易陷入“无感知陈旧”。

**DAUG** 从 Agent 调用工具（`read`、`edit`、`write`、`search`、`test`）的运行轨迹中提取隐式关联，融合 Git 共变更、静态 AST 依赖、显式符号引用与语义特征构建动态更新图。系统坚持**分级决策原则**：
1. **相关性不等于修改义务**：图引擎仅召回可能受影响的 Top-K 候选制品；
2. **独立陈旧验证器 (Staleness Verifier)**：针对具体语义陈述严格执行四值判定（`VALID`、`STALE`、`UNCERTAIN`、`NOT_APPLICABLE`）；
3. **最小补丁提案与哈希锚定**：绑定目标文件预期内容哈希，生成 Unified Diff 补丁提案；若文件发生外生修改（哈希漂移），立即终止操作；
4. **自强化与超边控制**：对系统推荐访问进行降权（0.05 vs 1.0），对批量任务构建超边（`task_hyperedge`），杜绝反馈回路与边组合爆炸。

---

## 2. 启动与阅读顺序 (Getting Started)

遵循十进制多 Agent 治理体系的标准阅读顺序：
1. [`00_入口/00_当前.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/00_入口/00_当前.md)（全库唯一权威当前状态入口）
2. [`HANDOFF.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/HANDOFF.md)（全库唯一全局交接总线）
3. [`AGENTS.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/AGENTS.md)（四方权力隔离与治理铁律）
4. [`01_需求与验收/00_索引.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/01_需求与验收/00_索引.md) 与 [`02_架构与合同/00_索引.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/02_架构与合同/00_索引.md)
5. [`07_运行记录/LOG.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/07_运行记录/LOG.md)（全库唯一纯追加过程流水账）

---

## 3. 快速上手 (Quickstart)

本实现完全基于 **Python 3.12 原生标准库**，零第三方外部包依赖。

### 3.1 一键运行 5 分钟端到端演练
```bash
# 执行完整演示流程（初始化账本 -> 轨迹导入 -> 构图 -> 召回 -> 验证 -> 补丁提议 -> 负对照 -> 生成报告）
./bin/daug demo run
# 或
python3 -m daug demo run
```
演练产物将自动落盘至 `runs/` 与 `07_运行记录/runs/`，包含交互式 `report.html`、`run_manifest.json` 与 SHA-256 清单。

### 3.2 运行自动化契约与场景测试集
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```
覆盖 12 项严苛测试：
- 幂等性、冲突检测与路径越界防御 (C01-C03)；
- 轨迹完整性与推荐来源约束 (C04-C05)；
- 构图确定性与离线哈希漂移拦截 (C06-C07)；
- 高危资产策略拦截与大任务超边控制 (C09-C10)；
- 跨模态接口变更召回 (D01)、局部重构负对照 0 误报 (D02)、提示词注入安全隔离 (D06)。

---

## 4. 十进制分层目录架构 (Decuple Layout)

```text
.
├── AGENTS.md                   # 行为规范、四方权力隔离与操作铁律
├── README.md                   # 工程总索引与架构概览
├── HANDOFF.md                  # 全库唯一全局交接总线
├── 00_入口/                    # 00_当前.md, 01_路线图.md, 02_决策记录.md, 03_开放问题与风险.md
├── 01_需求与验收/              # 01_MVP用户故事.md, 02_范围与非目标.md, 03_验收矩阵.md, 04_失败场景.md
├── 02_架构与合同/              # 00_系统方案基线.md, 01_系统架构与数据模型.md, 03_风险与治理方案.md, schemas/
├── 03_实现/                    # core/ (算法内核), cli/ (命令行工具), adapters/, plugins/, workspaces/
├── 04_测试与验收/              # 01_测试策略.md, 02_人类验收脚本.md, tests/, fixtures/
├── 05_研究资产/                # reports/ (后续研发与论文规划), raw/ (参考资料), claims/, evidence/
├── 06_任务与交接/              # active/, completed/, records/, handoffs/
├── 07_运行记录/                # LOG.md (纯追加过程流水), runs/ (演练清单), artifacts/
├── 08_归档/                    # superseded/ (废弃资产), failed/ (失败尝试)
├── 09_提案与草稿/              # 经 Gate 批准前唯一的草案隔离区
└── templates/                  # 12 份标准治理对象模板库
```

---

## 5. 核心状态词宣布

- Event ingestion: **Tested**
- Offline replay: **Tested**
- Candidate ranking: **Tested on demo fixture**
- Staleness verification: **Tested on synthetic fixture**
- Patch proposal: **Tested**
- Patch application: **Not implemented (Strictly Propose Only)**
- Production enablement: **Not authorized**
