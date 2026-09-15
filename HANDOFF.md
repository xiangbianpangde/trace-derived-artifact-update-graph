# DAUG (Trace-Derived Artifact Update Graph) 项目交接文档 (HANDOFF.md)

- **来源线程**: `codex://threads/01a09d57-76e3-78f2-bf98-b159553d13db`
- **上游对话**: `chatgpt-conversation://6aa7412f-a59c-83e8-85c4-cee99d6f30da`（分支 · 文件自动更新方案）
- **当前版本**: v0.1-demo (Decuple Architecture)
- **交接日期**: 2026-09-14
- **当前工作区路径**: `/Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an`
- **治理标准**: 遵循 `project-init-handoff` 十进制治理体系与四方权力边界隔离规范

---

## 1. 项目背景与目标

在大模型长程编码（Long-horizon Agentic Coding）任务中，底层代码发生演进时，关联设计文档与契约常陷入无感知陈旧。本项目旨在验证 **DAUG（Trace-Derived Artifact Update Graph，轨迹驱动的动态制品更新图）** 技术方案：

1. **多模态图构建**：从 Agent 工具轨迹中挖掘行为信号，与 Git 共变更、静态依赖、显式引用融合，构建有方向、带变化类型的更新图；
2. **候选召回（Candidate Retrieval）**：仅负责根据代码差异召回潜在受影响制品（Top-K），明确“相关性不等于修改义务”；
3. **独立陈旧验证（Staleness Verification）**：针对候选制品中的具体语义陈述判定四值状态（`VALID` / `STALE` / `UNCERTAIN` / `NOT_APPLICABLE`）；
4. **最小补丁提案（Patch Proposal）**：绑定目标预期内容哈希，生成 Unified Diff 补丁提案（`PATCH_PROPOSED`）；
5. **只读安全边界**：默认 `propose_only`，绝无生产自动写回，防范自强化恶性反馈回路。

---

## 2. 单事实源与核心治理规范

1. **单事实源准则 (SSOT)**:
   - 全库唯一权威物理当前状态：[`00_入口/00_当前.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/00_入口/00_当前.md)。
   - 全库唯一纯追加过程流水账：[`07_运行记录/LOG.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/07_运行记录/LOG.md)。
   - 全库唯一当前全局交接入口：本文件 [`HANDOFF.md`](file:///Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/HANDOFF.md)。
2. **四方权力隔离**:
   - 人类用户 (Human Owner)：最终验收与实质授权；
   - 主协调 Agent (Coordinator)：拆解切片、复算哈希、暴露待决风险，**严禁自我批准**；
   - 实现 Agent (IMPL)：仅在白名单沙箱内实现，产出候选版本，**严禁直写 canonical**；
   - 审核 Agent (VAL)：独立视角盲审，交叉核对，出具封闭工程判定（`CONFORMANT` 等）。
3. **哈希约束与回滚保证**:
   - 补丁提案强制绑定目标制品 `expected_target_hash`，CAS 校验失败即触发 `HashConflictError`。

---

## 3. 十进制分层文件架构

```text
├── 00_目录.md                                       # 项目纯目录文件
├── README.md -> 00_目录.md                          # 软链接至 00_目录.md
├── AGENTS.md                                     # 行为规范、四方权力边界与操作铁律
├── HANDOFF.md                                    # 全库唯一全局交接总线
├── 00_入口/
│   ├── 00_当前.md                                # 全库唯一当前状态入口
│   ├── 00_目录.md -> ../00_目录.md               # 软链接至根目录 00_目录.md
│   ├── 01_路线图.md                              # P0~P3 研发阶段与四周规划
│   ├── 02_决策记录.md                            # 关键决策表 (DEC-0001 ~ DEC-0005)
│   └── 03_开放问题与风险.md                      # 风险登记表 (R-001 ~ R-006) 与 Q 清单
├── 01_需求与验收/
│   ├── 01_MVP用户故事.md                         # 核心业务闭环故事 (US-001 ~ US-005)
│   ├── 02_范围与非目标.md                        # 必须实现清单与明确非目标 (Non-Goals)
│   ├── 03_验收矩阵.md                            # 功能、安全、方法学、展示四维验收矩阵
│   ├── 04_失败场景.md                            # 故障场景与系统防御机制 (F-001 ~ F-008)
│   ├── 05_Gate清单与批准边界.md                  # G-001 ~ G-014 门禁规范
│   └── 07_错误处置与fail_closed.md               # 四档处置映射矩阵 (E-001 ~ E-021)
├── 02_架构与合同/
│   ├── 00_系统方案基线.md                        # 原总体技术方案基线
│   ├── 01_系统架构与数据模型.md                  # 原系统架构与 21 张表数据模型
│   ├── 03_风险与治理方案.md                      # 原风险与治理方案
│   ├── 04_可执行不变量.md                        # INV-001 ~ INV-017 不变量
│   └── schemas/                                  # SQLite DDL 与 tool_event Schema
├── 03_实现/
│   ├── core/                                     # 核心算法内核 (daug package)
│   ├── cli/                                      # 命令行入口脚本 (daug CLI)
│   ├── plugins/                                  # 宿主 Agent 插件扩展
│   │   └── pi/                                   # Pi Coding Agent 扩展镜像 (daug.ts)
│   └── workspaces/                               # 隔离沙箱工作区
├── 04_测试与验收/
│   ├── 01_测试策略.md                            # 评测与消融实验方案 (RQ1~RQ6)
│   ├── 02_人类验收脚本.md                        # 5 分钟端到端演练手册与验收清单
│   ├── tests/                                    # 自动化契约与场景测试集 (12 项)
│   └── fixtures/                                 # demo-repo, changes, traces, labels
├── 05_研究资产/
│   ├── reports/01_后续研发与论文规划.md          # 论文规划与后续演进
│   └── raw/参考资料.md                           # 理论与学术文献引用
├── 06_任务与交接/                                # active/, completed/, records/, handoffs/
├── 07_运行记录/
│   ├── LOG.md                                    # 纯追加过程事件流水账
│   └── runs/                                     # 历次演练产物 (demo-run-...)
├── 08_归档/                                      # superseded/, failed/
├── 09_提案与草稿/                                # 未经 Gate 批准的暂存隔离区
├── daug/                                         # 根目录兼容符号与核心包
├── bin/daug                                      # 根目录便捷执行脚本
├── extensions/                                   # Pi Agent 扩展目录符号 (daug.ts)
└── templates/                                    # 12 份标准治理对象模板库
```

---

## 4. 核心状态词对照

依据规范约定的六级状态词体系：

| 模块 / 环节 | 当前状态 | 依据与说明 |
| --- | --- | --- |
| 十进制分层治理架构 | **Canonicalized** | 00_入口 ~ 09_提案与草稿全层级建立并规范化归档 |
| 技术方案文档拆分 | **Canonicalized** | 原始巨型文档拆分归入 01、02、04、05 层级 |
| SQLite WAL 事件账本 | **Tested** | 21 张表 DDL 执行通过，支持幂等去重与确定性回放 |
| 轨迹校验与敏感脱敏 | **Tested** | Schema 校验完备，正则脱敏密钥与 Token |
| 图构建与特征融合 | **Tested** | 融合 Static、Reference、Trace，支持超边与自强化抑制 |
| 候选检索与特征解释 | **Tested on demo fixture & real trace (MRR 1.0000)** | 输出 Top-K 候选及 EdgeEvidence 解释树，真实 GAP Trace 验证 0 AST 召回反转有效，Autoresearch 优化后 MRR 达到 1.0000 |
| 独立陈旧验证器 | **Tested on synthetic fixture & real code** | 严格输出四值状态，负对照 0 误报，细粒度 Section / JSON Pointer / Symbol 锚点定位与动态 Symbol 漂移识别 |
| 最小补丁提案生成器 | **Tested** | 绑定 Expected Target Hash，基于动态符号对应生成 Unified Diff（无硬编码） |
| 补丁安全应用与回读校验 | **Tested with CAS Guard** | 严格受 CAS 预检防漂移保护，写回后执行回读 SHA-256 校验并生成审计凭据 |
| 日常工程开发工具链 (CLI & Hook & CI) | **Tested & Hardened** | `daug check`、`daug patch apply`、`daug hook install` 与 PR Check 工作流模板就绪；钩子已修复 core.hooksPath 感知、退出码语义与绝对路径解析三项阻断级缺陷 |
| 交互式 Web 审查工作台 (P2) | **Tested & Deployed** | `./bin/daug review` 启动本地审查工作台，支持分栏 Diff 查看、单次批准门禁与 CAS 原子回读 |
| Pi Coding Agent 插件扩展 | **Tested in Pi Runtime** | `extensions/daug.ts` 与 `~/.pi/agent/extensions/daug.ts` 已支持 `/daug review` 与实时阻断 |
| 自动化测试套件 (32项) | **Tested** | `python3 -m unittest discover -s tests` 32 项 100% 通过 (1.1s) |
| 学术基准与消融对比实验 (P1) | **Benchmarked & Validated** | RQ1~RQ5 消融实验完备，量化验证工具轨迹相较于纯 AST (0%) 的显著增益 |
| 学术论文 A / B 规划与草案 | **Drafted** | 论文 A 12 章完整初稿与论文 B 详细规划全部落盘归档至 05_研究资产 |
| 端到端演示演练 | **Tested** | `./bin/daug demo run` 成功落盘交互式报告与清单 |
| 生产环境授权 | **Developer Tooling Ready (Manual Gate)** | 严格保留人工确认，未经开发者逐项复核授权绝无全自动写回 |

---

## 5. 后续接手者操作指南

1. **一键运行端到端 Demo**:
   ```bash
   ./bin/daug demo run
   ```
2. **运行全量自动化测试套件**:
   ```bash
   python3 -m unittest discover -s tests -p "test_*.py" -v
   ```
3. **日常代码与文档陈旧检查 (`daug check`)**:
   ```bash
   # 检查暂存区代码变动对应的陈旧文档
   ./bin/daug check --staged --db demo.sqlite

   # 检查指定文件并自动提议补丁
   ./bin/daug check src/auth/user_context.ts --db demo.sqlite --propose
   ```
4. **查看与应用补丁 (`daug patch`)**:
   ```bash
   # 查看当前待处理补丁列表
   ./bin/daug patch list --db demo.sqlite

   # 查看补丁差异内容
   ./bin/daug patch show <patch_id> --db demo.sqlite

   # 人工确认并应用补丁 (CAS 自动防护)
   ./bin/daug patch apply <patch_id> --db demo.sqlite
   ```
5. **Git 预提交钩子管理 (`daug hook`)**:
   ```bash
   # 安装 pre-commit 钩子 (默认提醒模式，--strict 开启严格阻断)
   ./bin/daug hook install

   # 卸载 pre-commit 钩子
   ./bin/daug hook uninstall
   ```
6. **Pi Coding Agent 插件使用 (`extensions/daug.ts`)**:
   - 插件已安装至全局 `~/.pi/agent/extensions/daug.ts`；
   - 启动 `pi` 时，插件自动生效；
   - 在 Pi 对话中使用 `/daug status` 或 `/daug check` 检查当前工作区陈旧文档；
   - Agent 会在执行 `edit` / `write` 时自动触发更新图检查，并在发现陈旧时获得上下文注入与 UI 告警；
   - Agent 可直接调用 `daug_check` 与 `daug_patch` 工具执行精细化文档修复。


