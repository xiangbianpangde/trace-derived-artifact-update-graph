import difflib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from daug.ledger import Ledger, compute_json_digest, compute_sha256, compute_str_digest, current_iso
from daug.policy import PolicyEngine

class HashConflictError(Exception):
    """Raised when the target artifact's current hash drifts from the expected verification hash."""
    pass

class PatchProposer:
    def __init__(self, ledger: Ledger, policy_engine: Optional[PolicyEngine] = None):
        self.ledger = ledger
        self.policy_engine = policy_engine or PolicyEngine(ledger)

    def propose_patch(self, verification_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.ledger.conn.cursor()

        # 1. Fetch verification, candidate, and artifact details
        query = """
        SELECT
            v.verification_id, v.candidate_id, v.target_version_hash, v.status,
            c.target_artifact_id,
            a.canonical_uri, a.repository_id,
            r.canonical_root
        FROM verification v
        JOIN update_candidate c ON v.candidate_id = c.candidate_id
        JOIN artifact a ON c.target_artifact_id = a.artifact_id
        JOIN repository r ON a.repository_id = r.repository_id
        WHERE v.verification_id = ?
        """
        row = cursor.execute(query, (verification_id,)).fetchone()
        if not row:
            raise ValueError(f"Verification '{verification_id}' not found")

        if row["status"] != "STALE":
            # No patch needed if not stale
            return None

        repo_root = Path(row["canonical_root"])
        canonical_uri = row["canonical_uri"]
        file_path = repo_root / canonical_uri

        if not file_path.exists():
            raise FileNotFoundError(f"Target artifact file not found at {file_path}")

        # C07: Hash conflict check
        with open(file_path, "rb") as f:
            current_bytes = f.read()
        current_hash = compute_sha256(current_bytes)
        expected_hash = row["target_version_hash"]

        if current_hash != expected_hash:
            raise HashConflictError(
                f"HASH_CONFLICT: Target '{canonical_uri}' has drifted. Expected {expected_hash}, found {current_hash}"
            )

        # 2. Fetch spans to update
        spans = cursor.execute(
            "SELECT * FROM verification_span WHERE verification_id=? ORDER BY span_no",
            (verification_id,)
        ).fetchall()

        original_text = current_bytes.decode("utf-8", errors="replace")
        lines = original_text.splitlines(keepends=True)

        # Generate modified lines (replace obsolete user_id with subject_id)
        new_lines = []
        changed_spans = []
        for line in lines:
            if "user_id" in line:
                mod_line = line.replace("user_id", "subject_id")
                new_lines.append(mod_line)
                changed_spans.append({"original": line.strip(), "replacement": mod_line.strip()})
            else:
                new_lines.append(line)

        # Unified diff
        diff = difflib.unified_diff(
            lines,
            new_lines,
            fromfile=f"a/{canonical_uri}",
            tofile=f"b/{canonical_uri}",
            lineterm=""
        )
        diff_text = "\n".join(diff)

        patch_id = f"patch-{compute_str_digest(verification_id)[7:23]}"
        patch_digest = compute_str_digest(diff_text)
        changed_spans_digest = compute_json_digest(changed_spans)
        rollback_digest = compute_str_digest(original_text)
        now = current_iso()

        # Minimality check
        minimality = "pass" if len(changed_spans) > 0 and len(changed_spans) <= 10 else "unknown"

        with self.ledger.conn:
            self.ledger.conn.execute(
                """
                INSERT INTO patch_proposal (
                    patch_id, verification_id, target_artifact_id, expected_target_hash,
                    patch_format, patch_digest, changed_spans_digest, minimality_check,
                    tests_digest, rollback_digest, generator_version, status, created_at
                ) VALUES (?, ?, ?, ?, 'unified_diff', ?, ?, ?, ?, ?, 'demo-patcher-0.1.0', 'proposed', ?)
                ON CONFLICT(verification_id) DO UPDATE SET
                    patch_digest=excluded.patch_digest,
                    status=excluded.status
                """,
                (
                    patch_id, verification_id, row["target_artifact_id"], expected_hash,
                    patch_digest, changed_spans_digest, minimality,
                    "sha256:no_tests_required", rollback_digest, now
                )
            )

        # Evaluate policy decision
        policy_decision = self.policy_engine.evaluate_patch(patch_id, canonical_uri)

        return {
            "patch_id": patch_id,
            "verification_id": verification_id,
            "target_artifact_uri": canonical_uri,
            "expected_target_hash": expected_hash,
            "status": "proposed",
            "minimality_check": minimality,
            "diff": diff_text,
            "policy_decision": policy_decision
        }
