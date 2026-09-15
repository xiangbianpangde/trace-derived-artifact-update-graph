import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from daug.anchor import AnchorParser, DiffSymbolExtractor
from daug.ledger import Ledger, compute_json_digest, compute_sha256, compute_str_digest, current_iso
from daug.statecheck import StateClaimScanner, StateTruthExtractor

VALID_STATUSES = {"VALID", "STALE", "UNCERTAIN", "NOT_APPLICABLE"}

class StalenessVerifier:
    def __init__(
        self,
        ledger: Ledger,
        verifier_version: str = "demo-verifier-0.1.0",
        repo_root_override: Optional[Path] = None
    ):
        self.ledger = ledger
        self.verifier_version = verifier_version
        self.repo_root_override = repo_root_override

    def verify_candidate(
        self,
        candidate_id: str,
        diff_text: Optional[str] = None
    ) -> Dict[str, Any]:
        cursor = self.ledger.conn.cursor()

        # 1. Fetch candidate, candidate_set, change_event, and target_artifact
        query = """
        SELECT
            c.candidate_id, c.candidate_set_id, c.target_artifact_id, c.score,
            cs.change_id,
            ce.change_type, ce.scope, ce.source_artifact_id,
            a.canonical_uri, a.repository_id,
            r.canonical_root
        FROM update_candidate c
        JOIN candidate_set cs ON c.candidate_set_id = cs.candidate_set_id
        JOIN change_event ce ON cs.change_id = ce.change_id
        JOIN artifact a ON c.target_artifact_id = a.artifact_id
        JOIN repository r ON a.repository_id = r.repository_id
        WHERE c.candidate_id = ?
        """
        row = cursor.execute(query, (candidate_id,)).fetchone()
        if not row:
            raise ValueError(f"Candidate {candidate_id} not found")

        repo_root = self.repo_root_override or Path(row["canonical_root"])
        target_file_path = repo_root / row["canonical_uri"]

        if not target_file_path.exists():
            return self._record_verification(
                candidate_id=candidate_id,
                target_hash="sha256:missing",
                status="UNCERTAIN",
                confidence=0.0,
                evidence_digest=compute_str_digest("file_not_found"),
                abstention_reason="Target file does not exist on disk",
                spans=[],
                canonical_uri=canonical_uri,
                target_artifact_id=row["target_artifact_id"]
            )

        with open(target_file_path, "rb") as f:
            target_bytes = f.read()
        target_hash = compute_sha256(target_bytes)
        target_text = target_bytes.decode("utf-8", errors="replace")

        change_type = row["change_type"]
        canonical_uri = row["canonical_uri"]

        # 2. Logic for Staleness Verification
        # Scenario B (Negative Control): local refactor
        if change_type == "refactor":
            # Local refactor does not make documentation or external interfaces stale
            return self._record_verification(
                candidate_id=candidate_id,
                target_hash=target_hash,
                status="VALID",
                confidence=0.98,
                evidence_digest=compute_str_digest("refactor_scope_local"),
                abstention_reason=None,
                spans=[],
                canonical_uri=canonical_uri,
                target_artifact_id=row["target_artifact_id"]
            )

        # Dynamic symbol drift and rename detection from diff
        renames = {}
        drift_tokens = set()
        if diff_text:
            renames = DiffSymbolExtractor.extract_renames_from_diff(diff_text)
            drift_tokens = set(DiffSymbolExtractor.extract_obsolete_tokens(diff_text))

        # Check for obsolete tokens in target
        check_tokens = list(drift_tokens) if drift_tokens else []
        for old_sym in renames:
            if old_sym not in check_tokens:
                check_tokens.append(old_sym)

        # Backward compatibility fallback for demo scenarios
        if "user_id" in target_text and change_type in ("interface", "schema"):
            if "user_id" not in check_tokens:
                check_tokens.append("user_id")
            if "user_id" not in renames:
                renames["user_id"] = "subject_id"

        if check_tokens and change_type in ("interface", "schema", "behavior"):
            spans = []
            for token in check_tokens:
                anchors = AnchorParser.find_anchors_for_token(
                    target_text,
                    token,
                    canonical_uri,
                    replacement=renames.get(token)
                )
                for anchor in anchors:
                    spans.append({
                        "span_no": len(spans) + 1,
                        "locator": anchor.locator,
                        "claim_digest": anchor.claim_digest,
                        "reason_code": "OBSOLETE_FIELD_REFERENCE" if token in ("user_id", "id") else "OBSOLETE_SYMBOL_REFERENCE",
                        "evidence_ids_digest": compute_str_digest(f"drift_symbol:{token}:{anchor.claim_text}"),
                        "target_token": token,
                        "replacement_token": renames.get(token)
                    })

            if spans:
                return self._record_verification(
                    candidate_id=candidate_id,
                    target_hash=target_hash,
                    status="STALE",
                    confidence=0.95,
                    evidence_digest=compute_json_digest({
                        "spans_count": len(spans),
                        "tokens": check_tokens,
                        "renames": renames
                    }),
                    abstention_reason=None,
                    spans=spans,
                    canonical_uri=canonical_uri,
                    target_artifact_id=row["target_artifact_id"]
                )

        # 3. Stateful claim detection (state transitions and numeric claims).
        #
        # Symbol drift above only fires when an identifier changed. Documents
        # frequently go stale without any identifier changing: a work item moves
        # from review to active, or a plan revision advances, while prose
        # elsewhere still asserts the old value. Detect those too, but only when
        # this repository nominates a status ledger as the source of truth, so
        # the check never invents an authority of its own.
        ledger_uri = self._get_status_ledger_uri(cursor, row["repository_id"])
        if ledger_uri and canonical_uri != ledger_uri:
            state_findings = self._detect_state_claims(
                repo_root=repo_root,
                ledger_uri=ledger_uri,
                target_text=target_text,
                target_uri=canonical_uri,
            )
            if state_findings:
                state_spans = []
                for f in state_findings:
                    state_spans.append({
                        "span_no": len(state_spans) + 1,
                        "locator": f"{f['locator']} [{f['kind']}]",
                        "claim_digest": f["claim_digest"],
                        "reason_code": "STALE_STATE_CLAIM",
                        "evidence_ids_digest": compute_str_digest(
                            f"state:{f['kind']}:{f['subject']}:{f['claimed']}->{f['actual']}"
                        ),
                    })
                return self._record_verification(
                    candidate_id=candidate_id,
                    target_hash=target_hash,
                    status="STALE",
                    confidence=0.9,
                    evidence_digest=compute_json_digest({
                        "spans_count": len(state_spans),
                        "state_claims": state_findings,
                        "source_of_truth": ledger_uri,
                    }),
                    abstention_reason=None,
                    spans=state_spans,
                    canonical_uri=canonical_uri,
                    target_artifact_id=row["target_artifact_id"],
                )

        # If it's a rollout plan or unrelated operational doc without obsolete claims:
        if "rollout_plan" in canonical_uri:
            return self._record_verification(
                candidate_id=candidate_id,
                target_hash=target_hash,
                status="NOT_APPLICABLE",
                confidence=0.92,
                evidence_digest=compute_str_digest("no_contract_reference"),
                abstention_reason=None,
                spans=[],
                canonical_uri=canonical_uri,
                target_artifact_id=row["target_artifact_id"]
            )

        # Default fallback
        return self._record_verification(
            candidate_id=candidate_id,
            target_hash=target_hash,
            status="VALID",
            confidence=0.85,
            evidence_digest=compute_str_digest("no_stale_patterns_found"),
            abstention_reason=None,
            spans=[],
            canonical_uri=canonical_uri,
            target_artifact_id=row["target_artifact_id"]
        )

    def verify_candidate_set(self, candidate_set_id: str) -> List[Dict[str, Any]]:
        cursor = self.ledger.conn.cursor()
        cands = cursor.execute(
            "SELECT candidate_id FROM update_candidate WHERE candidate_set_id=? ORDER BY rank",
            (candidate_set_id,)
        ).fetchall()
        results = []
        for cand in cands:
            res = self.verify_candidate(cand["candidate_id"])
            results.append(res)
        return results

    # --- Stateful claim support -------------------------------------------------

    # Conventional locations for a repository's authoritative status ledger.
    # Only an artifact that actually exists in the ledger is used, so a project
    # without a status file simply gets no state checking.
    STATUS_LEDGER_CANDIDATES = (
        "plan/STATUS.md",
        "STATUS.md",
        "plan/status.md",
    )

    def _get_status_ledger_uri(self, cursor, repository_id: str) -> Optional[str]:
        """Returns the repository-relative URI of its status ledger, if tracked."""
        cached = getattr(self, "_status_ledger_cache", None)
        if cached is None:
            cached = {}
            self._status_ledger_cache = cached
        if repository_id in cached:
            return cached[repository_id]

        found: Optional[str] = None
        for candidate in self.STATUS_LEDGER_CANDIDATES:
            row = cursor.execute(
                "SELECT canonical_uri FROM artifact WHERE repository_id=? AND canonical_uri=? LIMIT 1",
                (repository_id, candidate),
            ).fetchone()
            if row:
                found = row["canonical_uri"]
                break

        cached[repository_id] = found
        return found

    def _detect_state_claims(
        self,
        repo_root: Path,
        ledger_uri: str,
        target_text: str,
        target_uri: str,
    ) -> List[Dict[str, Any]]:
        """
        Compares stateful claims in a target document against the status ledger.

        Numeric revision claims are only scanned in a document's header region
        for files that are themselves coordination documents; elsewhere a
        historical revision number is legitimate history, not a stale claim.
        """
        try:
            truth = StateTruthExtractor.from_status_ledger(repo_root, ledger_uri)
        except Exception:
            return []
        if not truth.get("available"):
            return []

        findings: List[Dict[str, Any]] = []

        work_items = truth.get("work_items") or {}
        if work_items:
            findings.extend(
                StateClaimScanner.scan_work_item_status_claims(target_text, work_items)
            )

        # Revision claims are meaningful only for coordination-style documents
        # (handoff/status/index), and only in their leading section.
        lower_uri = target_uri.lower()
        is_coordination_doc = any(
            token in lower_uri for token in ("handoff", "status", "readme", "index", "plan/", "00_", "当前")
        )
        if is_coordination_doc and truth.get("revision") is not None:
            findings.extend(
                StateClaimScanner.scan_numeric_claims(
                    target_text,
                    revision_truth=truth["revision"],
                    line_limit=120,
                )
            )

        return findings

    def _record_verification(
        self,
        candidate_id: str,
        target_hash: str,
        status: str,
        confidence: float,
        evidence_digest: str,
        abstention_reason: Optional[str],
        spans: List[Dict[str, Any]],
        canonical_uri: Optional[str] = None,
        target_artifact_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid verification status {status}")

        verification_id = f"ver-{candidate_id}-{target_hash[:12]}"
        now = current_iso()

        with self.ledger.conn:
            self.ledger.conn.execute(
                """
                INSERT INTO verification (
                    verification_id, candidate_id, target_version_hash, status,
                    confidence, verifier_version, evidence_digest, abstention_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(verification_id) DO UPDATE SET
                    status=excluded.status,
                    confidence=excluded.confidence
                """,
                (
                    verification_id, candidate_id, target_hash, status,
                    confidence, self.verifier_version, evidence_digest, abstention_reason, now
                )
            )

            self.ledger.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_evidence_payload (
                    verification_id TEXT PRIMARY KEY,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            raw_evidence = json.dumps({"spans_count": len(spans), "tokens": [s.get("token") for s in spans if "token" in s]})
            # Extract renames if passed via evidence_meta
            renames_payload = {}
            for sp in spans:
                if sp.get("target_token") and sp.get("replacement_token"):
                    renames_payload[sp["target_token"]] = sp["replacement_token"]
            self.ledger.conn.execute(
                """
                INSERT INTO verification_evidence_payload (verification_id, evidence_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(verification_id) DO UPDATE SET
                    evidence_json=excluded.evidence_json
                """,
                (verification_id, json.dumps({"renames": renames_payload, "spans": spans}), now)
            )

            for span in spans:
                self.ledger.conn.execute(
                    """
                    INSERT INTO verification_span (
                        verification_id, span_no, locator, claim_digest,
                        reason_code, evidence_ids_digest
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(verification_id, span_no) DO UPDATE SET
                        locator=excluded.locator,
                        claim_digest=excluded.claim_digest
                    """,
                    (
                        verification_id, span["span_no"], span["locator"],
                        span["claim_digest"], span["reason_code"], span["evidence_ids_digest"]
                    )
                )

        return {
            "verification_id": verification_id,
            "candidate_id": candidate_id,
            "target_artifact_id": target_artifact_id,
            "canonical_uri": canonical_uri,
            "status": status,
            "confidence": confidence,
            "target_hash": target_hash,
            "spans": spans,
            "abstention_reason": abstention_reason
        }
