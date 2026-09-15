# Git 钩子安全接入指南 (Hook Integration Guide)

- **适用版本**: DAUG v0.1+（含 `EXIT_INFRA` 退出码语义与共享钩子目录门禁）
- **更新日期**: 2026-09-15
- **适用场景**: 将 DAUG 陈旧检查挂载到正在活跃开发的真实仓库

---

## 1. 为什么不能直接运行 `daug hook install`

早期实现的钩子存在三个**阻断级缺陷**，已在 `PROC-0012` 中修复。若在未更新的版本上直接安装，会遇到以下问题：

| 缺陷 | 现象 | 根因 | 当前状态 |
| --- | --- | --- | --- |
| 忽略 `core.hooksPath` | 安装提示成功，但 commit 时钩子**从不执行** | 硬编码写入 `.git/hooks/`，而 Git 实际从 `core.hooksPath` 读取 | ✅ 已修复（改用 `git rev-parse --git-path hooks`） |
| warn-only 误阻断提交 | 终端无提示，commit 被静默拒绝 | 钩子末尾命令的退出码成为钩子退出码，`daug` 报错返回 1 时被 Git 视为阻断 | ✅ 已修复（显式退出码契约） |
| 找不到 `daug` | 钩子三个探测分支全部失败，静默退出 | 依赖 `PATH` 与相对路径 `./bin/daug`，钩子运行时 CWD/PATH 不可预测 | ✅ 已修复（写入绝对路径入口） |

---

## 2. 退出码语义契约

`daug check` 严格区分「仓库状态」与「工具能否运行」，这决定钩子是否阻断提交：

| 退出码 | 常量 | 含义 | warn-only 钩子 | strict 钩子 |
| --- | --- | --- | --- | --- |
| `0` | `EXIT_OK` | 无陈旧，或发现陈旧但未启用 `--fail-on-stale` | 放行 | 放行 |
| `1` | `EXIT_STALE` | 发现陈旧且启用了 `--fail-on-stale` | 放行 | **阻断提交** |
| `3` | `EXIT_INFRA` | DAUG 无法运行（账本缺失、无图快照、参数错误） | 放行 | **阻断提交**（fail-closed） |
| 其它 | — | 崩溃或信号中断 | 放行 | **阻断提交**（fail-closed） |

**设计原则**：基础设施故障绝不能伪装成「代码陈旧」。这保证了 warn-only 模式在任何异常下都不会打断你的正常开发节奏。

---

## 3. 安全接入步骤（推荐流程）

### 3.1 前置检查

```bash
# 1. 确认是否配置了 core.hooksPath（可能来自全局配置）
git config --get core.hooksPath

# 2. 查看 Git 实际读取钩子的目录
git rev-parse --path-format=absolute --git-path hooks
```

若输出指向仓库**之外**的路径（例如 `~/.codex/git-hooks`），说明该目录被多个仓库共享。

### 3.2 为仓库分配独立钩子目录

```bash
cd /path/to/your-repo

# 给当前仓库分配仓库内的钩子目录，避免污染共享目录
git config core.hooksPath .githooks
```

### 3.3 安装钩子（先 warn-only）

```bash
# 建议显式指定账本路径，避免依赖自动发现
/path/to/daug/bin/daug hook install \
  --repo /path/to/your-repo \
  --type pre-commit \
  --db /path/to/ledger.sqlite
```

预期输出：

```
[hook-install] Installed DAUG 'pre-commit' hook in '/path/to/your-repo/.githooks/pre-commit' (warn-only ...).
[hook-install] Warn-only mode: prints findings but never blocks the commit.
```

### 3.4 验证钩子真实生效

不要只相信安装提示，必须**实证**钩子被 Git 调用：

```bash
cd /path/to/your-repo
echo "test" >> some-file.ts
git add some-file.ts
git commit -m "verify hook fires"
# 观察终端是否出现 DAUG Staleness Check 输出
```

### 3.5 观察期后再启用 strict

在 warn-only 下运行一段时间，确认误报率可接受后：

```bash
/path/to/daug/bin/daug hook install --repo /path/to/your-repo --type pre-commit --db /path/to/ledger.sqlite --strict
```

### 3.6 卸载

```bash
/path/to/daug/bin/daug hook uninstall --repo /path/to/your-repo --type pre-commit
```

---

## 4. 共享钩子目录的安全门禁

当 `core.hooksPath` 指向仓库外部时，`hook install` 会**拒绝安装**并给出修复建议：

```
[hook-install] Refusing to install: git resolves hooks to '/Users/you/.git-hooks',
which is outside this repository (core.hooksPath = '/Users/you/.git-hooks').
[hook-install] Installing there would affect every repository using that path.
[hook-install] Preferred fix - give this repository its own hook directory:
[hook-install]   git -C '/path/to/repo' config core.hooksPath .githooks
```

这是有意为之的**跨仓库变更保护**。若确实需要写入共享目录（例如集中式团队钩子），显式承担风险：

```bash
daug hook install --repo /path/to/repo --allow-shared-hooks
```

---

## 5. 故障排查

| 现象 | 检查项 |
| --- | --- |
| 安装了但 commit 时无任何输出 | 执行 `git rev-parse --git-path hooks`，确认钩子文件确实在该目录 |
| commit 被无理由阻断 | 直接运行 `sh <hooks-dir>/pre-commit; echo $?` 查看真实退出码 |
| 提示找不到 CLI | 钩子内写入的是绝对路径，确认该路径仍存在（`DAUG_ENTRY` 变量） |
| 提示账本缺失 | 用 `--db` 重新安装，或在仓库放置 `.daug.sqlite` |

---

## 6. 在活跃开发仓库中的实践建议

对于**正在高频迭代**的仓库（如 GAP Context Pager skills）：

1. **先重建账本**：`daug init` 后执行 `daug graph build`，并确保 `.gitignore` 中的产物目录（如 `gap/`、`dist/`）不被登记为制品；
2. **warn-only 起步**：先积累误报率数据，这也正是论文 B 所需的真实使用观测（接受率 AR、审查耗时）；
3. **strict 谨慎开启**：仅在确认无误报后启用，避免高频开发被打断；
4. **钩子目录入库**：将 `.githooks/` 提交到仓库，使团队成员获得一致体验。
