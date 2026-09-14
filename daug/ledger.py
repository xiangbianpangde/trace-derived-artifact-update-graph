import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "outputs/trace-derived-artifact-update-graph-demo-v0.1/schemas/sqlite_schema.sql"

class IdempotencyConflictError(Exception):
    """Raised when an event with the same ID or (trace_id, sequence_no) differs in payload."""
    pass

class PathEscapeError(Exception):
    """Raised when an artifact path escapes the repository boundary."""
    pass

class ValidationError(Exception):
    """Raised when an event or model violates schema or business rules."""
    pass

def current_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def compute_sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

def compute_str_digest(text: str) -> str:
    return compute_sha256(text.encode("utf-8"))

def compute_json_digest(obj: Any) -> str:
    canonical_json = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return compute_str_digest(canonical_json)

class Ledger:
    def __init__(self, db_path: str = "demo.sqlite"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA journal_mode = WAL;")

    def init_db(self, schema_file: Optional[str] = None):
        path = Path(schema_file) if schema_file else SCHEMA_PATH
        if not path.exists():
            raise FileNotFoundError(f"Schema file not found at {path}")
        with open(path, "r", encoding="utf-8") as f:
            ddl = f.read()
        self.conn.executescript(ddl)
        self.conn.commit()

    def register_repository(self, repository_id: str, canonical_root: str) -> str:
        root_path = Path(canonical_root).resolve()
        if not root_path.exists():
            root_path.mkdir(parents=True, exist_ok=True)
        # Compute root digest based on path and file listing
        digest_data = f"{repository_id}:{root_path}"
        root_digest = compute_str_digest(digest_data)
        now = current_iso()

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO repository (repository_id, canonical_root, root_digest, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                  canonical_root=excluded.canonical_root,
                  root_digest=excluded.root_digest
                """,
                (repository_id, str(root_path), root_digest, now)
            )
        return root_digest

    def register_artifact(
        self,
        repository_id: str,
        canonical_uri: str,
        artifact_kind: str = "source_code",
        authority_class: str = "canonical",
        risk_class: str = "R2",
        write_policy: str = "REVIEW_REQUIRED"
    ) -> str:
        # Check path escape
        repo_row = self.conn.execute("SELECT canonical_root FROM repository WHERE repository_id=?", (repository_id,)).fetchone()
        if repo_row:
            repo_root = Path(repo_row["canonical_root"]).resolve()
            target_path = (repo_root / canonical_uri).resolve()
            try:
                target_path.relative_to(repo_root)
            except ValueError:
                raise PathEscapeError(f"Path {canonical_uri} escapes repository boundary {repo_root}")

        artifact_id = f"artifact-{canonical_uri.replace('/', '-').replace('.', '-')}"
        now = current_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO artifact (
                    artifact_id, repository_id, canonical_uri, artifact_kind,
                    authority_class, risk_class, write_policy, first_observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, canonical_uri) DO UPDATE SET
                    artifact_kind=excluded.artifact_kind,
                    risk_class=excluded.risk_class
                """,
                (artifact_id, repository_id, canonical_uri, artifact_kind, authority_class, risk_class, write_policy, now)
            )
        return artifact_id

    def record_artifact_version(self, artifact_id: str, content_hash: str, size_bytes: Optional[int] = None) -> str:
        version_id = f"ver-{artifact_id}-{content_hash[:16]}"
        now = current_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO artifact_version (
                    artifact_version_id, artifact_id, content_hash, size_bytes, observed_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(artifact_id, content_hash) DO NOTHING
                """,
                (version_id, artifact_id, content_hash, size_bytes, now)
            )
        return version_id

    def register_trace_run(
        self,
        trace_id: str,
        task_id: str,
        repository_id: str,
        started_at: str,
        origin_mode: str = "organic",
        collector_version: str = "demo-collector-0.1.0",
        completeness: str = "complete",
        trace_digest: Optional[str] = None
    ):
        now = current_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO trace_run (
                    trace_id, task_id, repository_id, started_at,
                    origin_mode, collector_version, completeness, trace_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    completeness=excluded.completeness,
                    trace_digest=excluded.trace_digest
                """,
                (trace_id, task_id, repository_id, started_at, origin_mode, collector_version, completeness, trace_digest, now)
            )

    def append_tool_event(self, event: Dict[str, Any]) -> Tuple[str, bool]:
        """
        Inserts tool event with idempotency and boundary checks.
        Returns (event_id, is_duplicate).
        """
        event_id = event.get("event_id")
        trace_id = event.get("trace_id")
        seq_no = event.get("sequence_no")
        repo_id = event.get("repository_id")
        operation = event.get("operation")
        origin = event.get("access_origin", "organic")
        rec_id = event.get("recommendation_id")

        if not event_id or not trace_id or seq_no is None or not repo_id or not operation:
            raise ValidationError("Missing required event fields (event_id, trace_id, sequence_no, repository_id, operation)")

        # C05: recommendation check
        if origin == "system_recommended" and not rec_id:
            raise ValidationError(f"Event {event_id} has access_origin 'system_recommended' but lacks recommendation_id")

        # C03: path escape check and resolve artifact_id
        artifact_path = event.get("artifact_path")
        artifact_id = event.get("artifact_id")
        if artifact_path:
            repo_row = self.conn.execute("SELECT canonical_root FROM repository WHERE repository_id=?", (repo_id,)).fetchone()
            if repo_row:
                repo_root = Path(repo_row["canonical_root"]).resolve()
                norm_path = (repo_root / artifact_path).resolve()
                try:
                    norm_path.relative_to(repo_root)
                except ValueError:
                    raise PathEscapeError(f"Target path '{artifact_path}' escapes repository boundary '{repo_root}'")

            # Look up registered artifact_id
            art_row = self.conn.execute(
                "SELECT artifact_id FROM artifact WHERE repository_id=? AND canonical_uri=?",
                (repo_id, artifact_path)
            ).fetchone()
            if art_row:
                artifact_id = art_row["artifact_id"]
        elif artifact_id:
            check_art = self.conn.execute("SELECT 1 FROM artifact WHERE artifact_id=?", (artifact_id,)).fetchone()
            if not check_art:
                artifact_id = None

        # C04: edit/write missing hashes -> incomplete trace
        if operation in ("edit", "write"):
            if not event.get("before_hash") or not event.get("after_hash"):
                with self.conn:
                    self.conn.execute("UPDATE trace_run SET completeness='partial' WHERE trace_id=?", (trace_id,))

        event_digest = compute_json_digest({
            "event_id": event_id,
            "trace_id": trace_id,
            "sequence_no": seq_no,
            "operation": operation,
            "path": artifact_path,
            "input_digest": event.get("input_digest"),
            "output_digest": event.get("output_digest")
        })

        # C01 & C02: check duplicate
        existing = self.conn.execute(
            "SELECT event_id, event_digest FROM tool_event WHERE trace_id=? AND sequence_no=?",
            (trace_id, seq_no)
        ).fetchone()

        if existing:
            if existing["event_id"] == event_id and existing["event_digest"] == event_digest:
                return (existing["event_id"], True) # idempotent pass
            else:
                raise IdempotencyConflictError(
                    f"Conflict for (trace_id={trace_id}, seq={seq_no}): existing event {existing['event_id']} differs from incoming {event_id}"
                )

        now = current_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO tool_event (
                    event_id, trace_id, repository_id, sequence_no, parent_event_id,
                    occurred_at, tool_name, operation, artifact_id, artifact_path,
                    target_selector, input_digest, output_digest, before_hash, after_hash,
                    diff_digest, result_status, exit_code, access_origin, recommendation_id,
                    collector_version, payload_policy, event_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, trace_id, repo_id, seq_no, event.get("parent_event_id"),
                    event.get("occurred_at", now), event.get("tool_name"), operation,
                    artifact_id, artifact_path, event.get("target_selector"),
                    event.get("input_digest"), event.get("output_digest"),
                    event.get("before_hash"), event.get("after_hash"), event.get("diff_digest"),
                    event.get("result_status", "success"), event.get("exit_code", 0),
                    origin, rec_id, event.get("collector_version", "demo-collector-0.1.0"),
                    event.get("payload_policy", "metadata-plus-bounded-diff-v1"),
                    event_digest, now
                )
            )
        return (event_id, False)

    def record_change_event(
        self,
        change_id: str,
        source_artifact_id: str,
        change_type: str,
        impact_score: float = 0.8,
        scope: str = "file",
        trace_id: Optional[str] = None,
        before_version_id: Optional[str] = None,
        after_version_id: Optional[str] = None,
        classifier_source: str = "deterministic",
        classifier_confidence: float = 1.0,
        input_digest: str = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    ):
        now = current_iso()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO change_event (
                    change_id, trace_id, source_artifact_id, before_version_id, after_version_id,
                    change_type, impact_score, scope, classifier_source, classifier_confidence,
                    input_digest, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(change_id) DO UPDATE SET
                    change_type=excluded.change_type,
                    impact_score=excluded.impact_score
                """,
                (
                    change_id, trace_id, source_artifact_id, before_version_id, after_version_id,
                    change_type, impact_score, scope, classifier_source, classifier_confidence,
                    input_digest, now
                )
            )

    def close(self):
        self.conn.close()
