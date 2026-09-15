"""
daug.statecheck - State-transition and numeric-claim staleness detection.

The symbol-drift verifier in `daug.verifier` only catches obsolete identifiers
(renamed fields, removed functions). It is blind to a second, very common class
of drift in long-horizon agent work: **stateful claims**.

Two concrete patterns motivate this module, both observed in real repositories:

1. State transitions. A status ledger moves a work item from `review` to
   `active`. A separate document asserts "WU-0013 is under review". The prose is
   now false, yet it shares no identifier with the code diff, so symbol matching
   never fires.

2. Numeric claims. A document says "Plan revision: 60" while the plan is now at
   revision 104. No symbol changed; only a number.

This module keeps the same governance posture as the rest of DAUG: it only
*detects and reports* contradictions between a tracked source of truth and
claims written elsewhere. It never rewrites prose, and it abstains whenever it
cannot parse a value confidently.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from daug.ledger import compute_str_digest

# Status vocabulary. Ordered loosely from least to most "settled"; the order is
# not used to judge correctness, only to classify transitions for reporting.
STATUS_WORDS = [
    "verified", "active", "review", "blocked", "pending", "done",
    "in_progress", "completed", "rejected", "abandoned",
]

# A work item identifier such as WU-0013, TASK-42, DEC-0005.
WORK_ITEM_RE = re.compile(r"\b([A-Z]{2,6}-\d{3,6})\b")

# "revision" style counters, with flexible separators.
REVISION_CLAIM_RE = re.compile(
    r"(?i)\brevision[\s:=]*(?:is\s+)?[`\"']?(\d{1,7})[`\"']?"
)

# Explicit "Plan revision: N" phrasing used in handoff documents.
PLAN_REVISION_RE = re.compile(
    r"(?i)\bplan[\s_-]*revision[\s:=]*[`\"']?(\d{1,7})[`\"']?"
)

# YAML frontmatter block at the very top of a document.
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> Dict[str, str]:
    """Extracts flat `key: value` pairs from a leading YAML frontmatter block."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    fields: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value and not value.startswith(("[", "{")):
            fields[key] = value
    return fields


def parse_status_table(text: str) -> Dict[str, str]:
    """
    Extracts work-item -> status pairs from a Markdown status ledger table.

    GAP's `plan/STATUS.md` is the canonical shape: a pipe table whose first
    column holds a backticked work-item ID and that carries a dedicated status
    column. The status column is located by header name rather than by a fixed
    index so the parser survives column reordering.
    """
    results: Dict[str, str] = {}
    header_cols: Optional[List[str]] = None
    status_idx: Optional[int] = None
    id_idx: Optional[int] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            # Table ended; allow a later table to be parsed independently.
            header_cols = None
            status_idx = None
            id_idx = None
            continue

        cells = [c.strip() for c in line.strip("|").split("|")]

        # Separator row (|---|---|).
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue

        if header_cols is None:
            header_cols = [c.lower() for c in cells]
            for idx, name in enumerate(header_cols):
                if name in ("id", "工作单元", "item"):
                    id_idx = idx
                if name in ("状态", "status", "state"):
                    status_idx = idx
            continue

        if id_idx is None or status_idx is None:
            continue
        if len(cells) <= max(id_idx, status_idx):
            continue

        item_cell = cells[id_idx].strip("`").strip()
        status_cell = cells[status_idx].strip().strip("`").strip().lower()
        if item_cell and status_cell in STATUS_WORDS:
            results[item_cell] = status_cell

    return results


class StateClaimScanner:
    """
    Scans a target document for stateful claims that can be checked against a
    tracked source of truth.
    """

    @staticmethod
    def scan_work_item_status_claims(
        text: str,
        known_statuses: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        Finds prose assertions of the form "WU-0013 (active)" or
        "`WU-0013`（active）" and compares them with the authoritative status.

        Only fires when the document names a status word adjacent to the work
        item, so a bare mention of `WU-0013` is not treated as a claim.
        """
        findings: List[Dict[str, Any]] = []
        lines = text.splitlines()

        for line_no, line in enumerate(lines, start=1):
            if not WORK_ITEM_RE.search(line):
                continue
            for item_id in set(WORK_ITEM_RE.findall(line)):
                truth = known_statuses.get(item_id)
                if not truth:
                    continue

                # Look for a status word near the work item on the same line.
                lowered = line.lower()
                claimed = None
                for word in STATUS_WORDS:
                    # Require the word to appear as a standalone token.
                    if re.search(rf"(?<![A-Za-z_]){re.escape(word)}(?![A-Za-z_])", lowered):
                        claimed = word
                        break
                if claimed is None or claimed == truth:
                    continue

                findings.append({
                    "kind": "work_item_status_mismatch",
                    "locator": f"line:{line_no}",
                    "claimed": claimed,
                    "actual": truth,
                    "subject": item_id,
                    "claim_text": line.strip(),
                    "claim_digest": compute_str_digest(line.strip()),
                })

        return findings

    @staticmethod
    def scan_numeric_claims(
        text: str,
        revision_truth: Optional[int],
        line_limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Finds numeric claims about a revision counter and compares them with the
        authoritative value.

        `line_limit` restricts scanning to the first N lines, which is useful for
        documents whose header asserts current state and whose body contains
        historical values that are correct as history.
        """
        findings: List[Dict[str, Any]] = []
        if revision_truth is None:
            return findings

        lines = text.splitlines()
        scan_lines = lines[:line_limit] if line_limit else lines

        for line_no, line in enumerate(scan_lines, start=1):
            for pattern, kind in (
                (PLAN_REVISION_RE, "plan_revision_mismatch"),
                (REVISION_CLAIM_RE, "revision_mismatch"),
            ):
                match = pattern.search(line)
                if not match:
                    continue
                try:
                    claimed = int(match.group(1))
                except (TypeError, ValueError):
                    continue
                if claimed == revision_truth:
                    continue
                findings.append({
                    "kind": kind,
                    "locator": f"line:{line_no}",
                    "claimed": claimed,
                    "actual": revision_truth,
                    "subject": "revision",
                    "claim_text": line.strip(),
                    "claim_digest": compute_str_digest(line.strip()),
                })
                break  # one finding per line is enough

        return findings


class StateTruthExtractor:
    """Extracts authoritative state from a designated source-of-truth artifact."""

    @staticmethod
    def from_status_ledger(repo_root: Path, relative_uri: str) -> Dict[str, Any]:
        """
        Reads a status ledger such as `plan/STATUS.md` and returns the
        authoritative revision plus the per-work-item status map.
        """
        path = repo_root / relative_uri
        if not path.is_file():
            return {"revision": None, "work_items": {}, "available": False}

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"revision": None, "work_items": {}, "available": False}

        revision: Optional[int] = None
        try:
            fields = parse_frontmatter(text)
            if "revision" in fields:
                revision = int(fields["revision"])
        except (TypeError, ValueError):
            revision = None

        return {
            "revision": revision,
            "work_items": parse_status_table(text),
            "available": True,
        }
