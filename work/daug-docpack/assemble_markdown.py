from hashlib import sha256
from pathlib import Path


ROOT = Path("outputs/trace-derived-artifact-update-graph-demo-v0.1")
OUTPUT = ROOT / "Trace-Derived-Artifact-Update-Graph-Demo-技术方案-v0.1.md"

PARTS = [
    ROOT / "docs/01-总体技术方案.md",
    ROOT / "docs/02-系统架构与数据模型.md",
    ROOT / "docs/03-MVP与Demo实施计划.md",
    ROOT / "docs/04-评测与消融实验方案.md",
    ROOT / "docs/05-风险与治理.md",
    ROOT / "docs/06-后续研发与论文规划.md",
    ROOT / "docs/07-Demo运行手册与验收清单.md",
    ROOT / "references/参考资料.md",
]


def demote_headings(markdown: str) -> str:
    lines = []
    in_fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("#"):
            prefix, separator, rest = line.partition(" ")
            if separator and set(prefix) == {"#"}:
                line = "#" + prefix + " " + rest
        lines.append(line)
    return "\n".join(lines).strip()


preamble = """# 轨迹驱动的动态制品更新图 Demo 技术方案与研究规划

版本：v0.1  
状态：方案草案  
更新日期：2026-09-14

## 文档说明

本合订版覆盖总体技术方案、系统架构与数据模型、MVP 与 Demo 实施计划、评测与消融实验、风险与治理、后续研发与论文规划，以及 Demo 运行和验收清单。

核心建议是先实现单仓库、离线回放、只读采集、补丁提案模式的 MVP。Artifact Update Graph 只负责召回可能受影响的制品；独立的 staleness verifier 判断具体陈述是否失效。MVP 不执行真实自动写回，也不把建议指标写成已有结果。

## 文档导航

1. 总体技术方案
2. 系统架构与数据模型
3. MVP 与 Demo 实施计划
4. 评测与消融实验方案
5. 风险与治理
6. 后续研发与论文规划
7. Demo 运行手册与验收清单
8. 参考资料
"""

sections = [preamble.strip()]
for part in PARTS:
    sections.append(demote_headings(part.read_text(encoding="utf-8")))

OUTPUT.write_text("\n\n---\n\n".join(sections) + "\n", encoding="utf-8")
manifest = ROOT / "MANIFEST.sha256"
entries = []
for path in sorted(p for p in ROOT.rglob("*") if p.is_file() and p != manifest):
    digest = sha256(path.read_bytes()).hexdigest()
    entries.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
manifest.write_text("\n".join(entries) + "\n", encoding="utf-8")
print(OUTPUT)
