"""
daug.anchor - Fine-grained claim-level anchors, document AST structure extraction,
and dynamic symbol drift / rename resolution.
"""

import difflib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple
from daug.ledger import compute_sha256, compute_str_digest

COMMON_KEYWORDS = {
    "const", "let", "var", "function", "return", "import", "export", "from",
    "class", "interface", "type", "async", "await", "public", "private", "protected",
    "string", "number", "boolean", "any", "void", "null", "undefined",
    "def", "class", "return", "import", "from", "self", "None", "True", "False"
}

IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")

@dataclass
class DocumentAnchor:
    anchor_type: str       # "section" | "json_pointer" | "symbol" | "line"
    locator: str           # e.g. "section:## Data Structure > line:7" or "json_pointer:/properties/user_id"
    context: str           # Section title or enclosing scope
    line_start: int        # 1-indexed
    line_end: int          # 1-indexed
    claim_text: str        # The raw text statement or claim
    claim_digest: str      # SHA-256 digest of normalized statement
    target_token: Optional[str] = None
    replacement_token: Optional[str] = None

class AnchorParser:
    """Parses structured documents into fine-grained claim anchors."""

    @staticmethod
    def parse_markdown(text: str) -> List[Dict[str, Any]]:
        """Parses markdown into hierarchical section blocks."""
        lines = text.splitlines()
        sections = []
        current_heading = "Top Level"
        heading_level = 0
        section_start = 1
        section_lines = []

        for idx, line in enumerate(lines, start=1):
            header_match = re.match(r"^(#{1,6})\s+(.*)$", line)
            if header_match:
                # Save previous section if it had content
                if section_lines:
                    sections.append({
                        "title": current_heading,
                        "level": heading_level,
                        "start_line": section_start,
                        "end_line": idx - 1,
                        "lines": section_lines
                    })
                heading_level = len(header_match.group(1))
                current_heading = line.strip()
                section_start = idx
                section_lines = [line]
            else:
                section_lines.append(line)

        if section_lines:
            sections.append({
                "title": current_heading,
                "level": heading_level,
                "start_line": section_start,
                "end_line": len(lines),
                "lines": section_lines
            })

        return sections

    @classmethod
    def find_anchors_for_token(
        cls,
        text: str,
        token: str,
        canonical_uri: str,
        replacement: Optional[str] = None
    ) -> List[DocumentAnchor]:
        """Locates all occurrences of a token in a document and binds them to fine-grained anchors."""
        lines = text.splitlines()
        anchors = []
        is_markdown = canonical_uri.endswith(".md") or canonical_uri.endswith(".markdown")
        is_json_schema = canonical_uri.endswith(".json") or "schema" in canonical_uri.lower()
        is_code = canonical_uri.endswith((".ts", ".js", ".py", ".go", ".rs"))

        if is_markdown:
            sections = cls.parse_markdown(text)
            for sec in sections:
                for rel_idx, line in enumerate(sec["lines"]):
                    abs_line = sec["start_line"] + rel_idx
                    if token in line:
                        # Extract list item or bullet info if applicable
                        sub_locator = f"line:{abs_line}"
                        if line.strip().startswith(("-", "*", "+")):
                            sub_locator = f"item (line:{abs_line})"
                        locator = f"section:{sec['title']} > {sub_locator}"
                        clean_claim = line.strip()
                        anchors.append(DocumentAnchor(
                            anchor_type="section",
                            locator=locator,
                            context=sec["title"],
                            line_start=abs_line,
                            line_end=abs_line,
                            claim_text=clean_claim,
                            claim_digest=compute_str_digest(clean_claim),
                            target_token=token,
                            replacement_token=replacement
                        ))
        elif is_json_schema:
            try:
                data = json.loads(text)
                # Check for properties or fields
                if isinstance(data, dict) and "properties" in data and token in data["properties"]:
                    prop_line = 1
                    for idx, line in enumerate(lines, start=1):
                        if f'"{token}"' in line:
                            prop_line = idx
                            break
                    locator = f"json_pointer:/properties/{token} (line:{prop_line})"
                    claim_str = json.dumps({token: data["properties"][token]}, sort_keys=True)
                    anchors.append(DocumentAnchor(
                        anchor_type="json_pointer",
                        locator=locator,
                        context=f"/properties/{token}",
                        line_start=prop_line,
                        line_end=prop_line,
                        claim_text=claim_str,
                        claim_digest=compute_str_digest(claim_str),
                        target_token=token,
                        replacement_token=replacement
                    ))
            except Exception:
                pass

        # Fallback if no specialized anchors found or for code / general text
        if not anchors:
            current_scope = "module"
            for idx, line in enumerate(lines, start=1):
                if is_code:
                    scope_match = re.search(r"\b(interface|class|function|def)\s+([A-Za-z0-9_]+)", line)
                    if scope_match:
                        current_scope = f"{scope_match.group(1)} {scope_match.group(2)}"
                if token in line:
                    clean_claim = line.strip()
                    if is_code:
                        locator = f"symbol:{current_scope} > line:{idx}"
                    else:
                        locator = f"line:{idx}"
                    anchors.append(DocumentAnchor(
                        anchor_type="symbol" if is_code else "line",
                        locator=locator,
                        context=current_scope,
                        line_start=idx,
                        line_end=idx,
                        claim_text=clean_claim,
                        claim_digest=compute_str_digest(clean_claim),
                        target_token=token,
                        replacement_token=replacement
                    ))

        return anchors

class DiffSymbolExtractor:
    """Extracts dynamic symbol renames and obsolete tokens from git diffs without hardcoding."""

    @classmethod
    def extract_renames_from_diff(cls, diff_text: str) -> Dict[str, str]:
        """
        Extracts token rename pairs from unified diff hunks.
        Pairs lines like:
          - export interface UserContext { user_id: string; }
          + export interface UserContext { subject_id: string; }
        producing: {"user_id": "subject_id"}
        """
        if not diff_text:
            return {}

        lines = diff_text.splitlines()
        renames = {}

        hunk_removals = []
        hunk_additions = []

        def process_hunk_pair(rem_lines, add_lines):
            # For each removed line, find the best corresponding added line
            used_add_indices = set()
            for r_line in rem_lines:
                r_tokens = [t for t in IDENTIFIER_RE.findall(r_line) if t not in COMMON_KEYWORDS]
                if not r_tokens:
                    continue
                best_sim = 0.3
                best_idx = None

                for a_idx, a_line in enumerate(add_lines):
                    if a_idx in used_add_indices:
                        continue
                    sim = difflib.SequenceMatcher(None, r_line, a_line).ratio()
                    if sim > best_sim:
                        best_sim = sim
                        best_idx = a_idx

                if best_idx is not None:
                    used_add_indices.add(best_idx)
                    a_line = add_lines[best_idx]
                    a_tokens = [t for t in IDENTIFIER_RE.findall(a_line) if t not in COMMON_KEYWORDS]
                    diff_r = [t for t in r_tokens if t not in a_tokens]
                    diff_a = [t for t in a_tokens if t not in r_tokens]
                    if len(diff_r) == 1 and len(diff_a) == 1:
                        renames[diff_r[0]] = diff_a[0]
                    elif diff_r and diff_a:
                        # Find closest token pair
                        for old_t in diff_r:
                            best_tok_sim = 0.0
                            best_new_t = None
                            for new_t in diff_a:
                                t_sim = difflib.SequenceMatcher(None, old_t, new_t).ratio()
                                if t_sim > best_tok_sim:
                                    best_tok_sim = t_sim
                                    best_new_t = new_t
                            if best_new_t:
                                renames[old_t] = best_new_t

        for line in lines:
            if line.startswith("@@"):
                if hunk_removals or hunk_additions:
                    process_hunk_pair(hunk_removals, hunk_additions)
                    hunk_removals = []
                    hunk_additions = []
            elif line.startswith("-") and not line.startswith("---"):
                hunk_removals.append(line[1:].strip())
            elif line.startswith("+") and not line.startswith("+++"):
                hunk_additions.append(line[1:].strip())

        if hunk_removals or hunk_additions:
            process_hunk_pair(hunk_removals, hunk_additions)

        return renames

    @classmethod
    def extract_obsolete_tokens(cls, diff_text: str) -> List[str]:
        """Extracts all removed tokens that are not present in the additions."""
        if not diff_text:
            return []
        removed = set()
        added = set()
        for line in diff_text.splitlines():
            if line.startswith("-") and not line.startswith("---"):
                removed.update(IDENTIFIER_RE.findall(line))
            elif line.startswith("+") and not line.startswith("+++"):
                added.update(IDENTIFIER_RE.findall(line))
        drift = removed - added - COMMON_KEYWORDS
        return sorted(list(drift))
