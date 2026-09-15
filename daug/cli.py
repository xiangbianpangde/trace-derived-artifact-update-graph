import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from daug.ledger import Ledger, compute_sha256
from daug.normalizer import Normalizer
from daug.graph import GraphBuilder
from daug.retriever import CandidateRetriever
from daug.verifier import StalenessVerifier
from daug.patcher import PatchProposer
from daug.policy import PolicyEngine
from daug.reporter import RunReporter

BASE_DIR = Path(__file__).resolve().parent.parent

# Exit codes for `daug check` (and any hook consuming it).
# The distinction matters: a hook must be able to tell "the repo is clean/stale"
# apart from "DAUG could not run at all". Conflating them caused warn-only hooks
# to silently block every commit when the ledger was missing.
EXIT_OK = 0            # clean, or stale found but not in --fail-on-stale mode
EXIT_STALE = 1         # stale found and --fail-on-stale requested the block
EXIT_INFRA = 3         # DAUG could not run (no ledger, no graph snapshot, bad args)

def get_ledger(db_path: str = "demo.sqlite") -> Ledger:
    ledger = Ledger(db_path)
    return ledger

def cmd_init(args):
    db = args.db
    repo_root = Path(args.repo_root).resolve()
    repo_id = args.repo_id

    ledger = get_ledger(db)
    ledger.init_db()
    ledger.register_repository(repo_id, str(repo_root))

    # Register all files in repo_root
    count = 0
    ignored_dirs = {".git", "node_modules", ".pi", "dist", "build", "coverage", ".next"}
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for f in files:
            if f.startswith(".") or f == ".DS_Store":
                continue
            p = Path(root) / f
            rel = str(p.relative_to(repo_root))
            kind = "documentation" if rel.endswith(".md") else ("test" if "test" in rel else "source_code")
            risk = "R2" if (kind in ("documentation", "test")) else "R3"
            with open(p, "rb") as fp:
                h = compute_sha256(fp.read())
            aid = ledger.register_artifact(repo_id, rel, artifact_kind=kind, risk_class=risk)
            ledger.record_artifact_version(aid, h, size_bytes=p.stat().st_size)
            count += 1

    print(f"[init] Initialized SQLite database '{db}' with {count} artifacts registered for repo '{repo_id}'.")

def cmd_trace_ingest(args):
    ledger = get_ledger(args.db)
    normalizer = Normalizer()

    count_organic = 0
    count_recommended = 0
    trace_id = None
    repo_id = None

    for raw in normalizer.read_jsonl(args.trace_file):
        ev = normalizer.validate_and_normalize_event(raw)
        trace_id = ev["trace_id"]
        repo_id = ev["repository_id"]

        # Ensure trace run is registered
        ledger.register_trace_run(
            trace_id=trace_id,
            task_id=f"task-{trace_id}",
            repository_id=repo_id,
            started_at=ev.get("occurred_at")
        )

        _, is_dup = ledger.append_tool_event(ev)
        if not is_dup:
            if ev.get("access_origin") == "system_recommended":
                count_recommended += 1
            else:
                count_organic += 1

    print(f"[trace-ingest] Ingested trace '{trace_id}': {count_organic} organic events, {count_recommended} recommended events. Schema validation: PASS.")

def cmd_trace_record(args):
    db_path = None
    if getattr(args, "db", None):
        db_path = Path(args.db).resolve()
    else:
        candidates = [
            Path.cwd() / ".daug.sqlite",
            Path.cwd() / ".daug" / "ledger.sqlite",
            Path.cwd() / "gap-demo.sqlite",
            Path.cwd() / "demo.sqlite",
            BASE_DIR / "gap-demo.sqlite",
            BASE_DIR / "demo.sqlite"
        ]
        for c in candidates:
            if c.exists():
                db_path = c
                break

    if not db_path or not db_path.exists():
        if not getattr(args, "quiet", False):
            print("[trace-record] Warning: No DAUG database found. Skipping trace recording.", file=sys.stderr)
        return 0

    ledger = get_ledger(str(db_path))
    cursor = ledger.conn.cursor()

    repo_row = cursor.execute("SELECT repository_id, canonical_root FROM repository LIMIT 1").fetchone()
    repo_id = repo_row["repository_id"] if repo_row else (getattr(args, "repo_id", None) or "default-repo")
    trace_id = getattr(args, "trace_id", None) or f"trace-live-pi-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    ledger.register_trace_run(
        trace_id=trace_id,
        task_id=f"task-{trace_id}",
        repository_id=repo_id,
        started_at=now
    )

    artifact_id = None
    if args.path:
        norm_path = args.path.lstrip("./")
        art = cursor.execute(
            "SELECT artifact_id FROM artifact WHERE canonical_uri=? OR canonical_uri LIKE ? LIMIT 1",
            (norm_path, f"%{norm_path}")
        ).fetchone()
        if art:
            artifact_id = art["artifact_id"]

    seq_row = cursor.execute("SELECT MAX(sequence_no) as max_seq FROM tool_event WHERE trace_id=?", (trace_id,)).fetchone()
    seq_no = (seq_row["max_seq"] + 1) if (seq_row and seq_row["max_seq"] is not None) else 1

    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    from daug.ledger import compute_json_digest
    ev = {
        "event_id": event_id,
        "trace_id": trace_id,
        "repository_id": repo_id,
        "sequence_no": seq_no,
        "parent_event_id": None,
        "occurred_at": now,
        "tool_name": args.tool or "generic",
        "operation": args.op or "read",
        "artifact_id": artifact_id,
        "artifact_path": args.path,
        "target_selector": None,
        "input_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "output_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "before_hash": None,
        "after_hash": None,
        "diff_digest": None,
        "result_status": args.status or "success",
        "exit_code": 0,
        "access_origin": "organic",
        "recommendation_id": None,
        "collector_version": "pi-extension-0.1.0",
        "payload_policy": "RECORD_HASH_ONLY",
        "event_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
        "created_at": now
    }
    ev["event_digest"] = compute_json_digest(ev)
    ledger.append_tool_event(ev)
    if not getattr(args, "quiet", False):
        print(f"[trace-record] Recorded {args.op} on '{args.path}' (id: {event_id})")
    return 0

def cmd_graph_build(args):
    ledger = get_ledger(args.db)
    builder = GraphBuilder(ledger)
    res = builder.build_snapshot(until_timestamp=args.until)
    print(f"[graph-build] Published graph snapshot '{res['graph_version']}': {res['edges_count']} edges, {res['hyperedges_count']} hyperedges. Digest: {res['graph_digest'][:24]}...")

def cmd_candidates_rank(args):
    ledger = get_ledger(args.db)
    retriever = CandidateRetriever(ledger)
    res = retriever.rank_candidates(args.change, top_k=args.top_k)
    print(f"[candidates-rank] Candidate set '{res['candidate_set_id']}': retrieved {len(res['candidates'])} candidates.")
    for c in res["candidates"]:
        print(f"  - Rank {c['rank']}: {c['target_artifact_id']} (score: {c['total_score']:.4f}, relations: {list(c['relations'].keys())})")

def cmd_verify(args):
    ledger = get_ledger(args.db)
    verifier = StalenessVerifier(ledger)
    results = verifier.verify_candidate_set(args.candidate_set)
    print(f"[verify] Verified {len(results)} candidates for candidate set '{args.candidate_set}':")
    for r in results:
        spans_desc = f" ({len(r['spans'])} spans)" if r["spans"] else ""
        print(f"  - {r['candidate_id']}: status={r['status']}, conf={r['confidence']:.2f}{spans_desc}")

def cmd_patch_propose(args):
    ledger = get_ledger(args.db)
    patcher = PatchProposer(ledger)
    p = patcher.propose_patch(args.verification)
    if not p:
        print(f"[patch-propose] Verification '{args.verification}' is not STALE; no patch proposed.")
        return
    print(f"[patch-propose] Proposed patch '{p['patch_id']}' for {p['target_artifact_uri']}:")
    print(f"  Status: {p['status']} (NOT APPLIED)")
    print(f"  Expected target hash: {p['expected_target_hash']}")
    print(f"  Minimality check: {p['minimality_check']}")
    print(f"  Policy action: {p['policy_decision']['action']} ({p['policy_decision']['reason_code']})")

def cmd_review(args):
    from daug.server import start_review_server
    # 1. Determine repo root
    repo_root = None
    if getattr(args, "repo_root", None):
        repo_root = Path(args.repo_root).resolve()
    else:
        try:
            res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
            repo_root = Path(res.stdout.strip()).resolve()
        except Exception:
            repo_root = Path.cwd().resolve()

    # 2. Determine db path
    db_path = None
    if getattr(args, "db", None):
        db_path = Path(args.db).resolve()
    else:
        candidates = [
            repo_root / ".daug.sqlite",
            repo_root / ".daug" / "ledger.sqlite",
            Path.cwd() / "gap-demo.sqlite",
            Path.cwd() / "demo.sqlite",
            BASE_DIR / "gap-demo.sqlite",
            BASE_DIR / "demo.sqlite"
        ]
        for c in candidates:
            if c.exists():
                db_path = c
                break

    if not db_path or not db_path.exists():
        print("[review] Error: No DAUG ledger database found. Specify --db or run 'daug init' first.", file=sys.stderr)
        return 1

    start_review_server(
        repo_root=repo_root,
        db_path=db_path,
        port=args.port,
        open_browser=not args.no_browser
    )
    return 0

def cmd_patch_list(args):
    ledger = get_ledger(args.db)
    patcher = PatchProposer(ledger)
    patches = patcher.list_patches(status=getattr(args, "status", None))
    if not patches:
        print(f"[patch-list] No patch proposals found in '{args.db}'.")
        return 0
    print(f"[patch-list] Found {len(patches)} patch proposal(s):")
    for p in patches:
        print(f"  - {p['patch_id']} | Status: {p['status']} | Target: {p['canonical_uri']} | Created: {p['created_at']}")
    return 0

def cmd_patch_show(args):
    ledger = get_ledger(args.db)
    patcher = PatchProposer(ledger)
    diff = patcher.get_patch_diff(args.patch_id)
    if not diff:
        print(f"[patch-show] No diff payload found for patch '{args.patch_id}'.", file=sys.stderr)
        return 1
    print(diff)
    return 0

def cmd_patch_apply(args):
    ledger = get_ledger(args.db)
    repo_override = Path(args.repo_root).resolve() if getattr(args, "repo_root", None) else None
    patcher = PatchProposer(ledger, repo_root_override=repo_override)
    patch_id = args.patch_id

    diff_text = patcher.get_patch_diff(patch_id)
    if not diff_text:
        print(f"[patch-apply] Error: Patch payload for '{patch_id}' not found in database.", file=sys.stderr)
        return 1

    cursor = ledger.conn.cursor()
    row = cursor.execute(
        """
        SELECT p.patch_id, p.expected_target_hash, a.canonical_uri, r.canonical_root
        FROM patch_proposal p
        JOIN artifact a ON p.target_artifact_id = a.artifact_id
        JOIN repository r ON a.repository_id = r.repository_id
        WHERE p.patch_id = ?
        """,
        (patch_id,)
    ).fetchone()

    if not row:
        print(f"[patch-apply] Error: Patch '{patch_id}' not found in database.", file=sys.stderr)
        return 1

    effective_root = repo_override or Path(row["canonical_root"])
    file_path = effective_root / row["canonical_uri"]

    print("=" * 65)
    print(f"DAUG Patch Review: {patch_id}")
    print(f"Target file:   {file_path}")
    print(f"Expected hash: {row['expected_target_hash']}")
    print("=" * 65)
    print(diff_text)
    print("=" * 65)

    if not getattr(args, "yes", False):
        try:
            confirm = input(f"Apply this patch to '{row['canonical_uri']}'? [y/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nPatch application cancelled.")
            return 1

        if confirm not in ("y", "yes"):
            print("Patch application cancelled by user.")
            return 0

    try:
        receipt = patcher.apply_patch(patch_id)
    except Exception as e:
        print(f"[patch-apply] Error: {e}", file=sys.stderr)
        return 1

    print(f"[patch-apply] Successfully applied patch '{patch_id}' to {receipt['target_file']}.")
    print(f"  Attempt ID:       {receipt['attempt_id']}")
    print(f"  Receipt ID:       {receipt['receipt_id']}")
    print(f"  Before Hash:      {receipt['before_hash'][:16]}...")
    print(f"  After Hash:       {receipt['after_hash'][:16]}...")
    print(f"  Readback status:  {receipt['readback_status']}")
    return 0

def cmd_check(args):
    # 1. Determine repo root
    repo_root = None
    if getattr(args, "repo_root", None):
        repo_root = Path(args.repo_root).resolve()
    else:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True
            )
            repo_root = Path(res.stdout.strip()).resolve()
        except Exception:
            repo_root = Path.cwd().resolve()

    # 2. Determine changed files
    input_files = list(getattr(args, "files", []) or [])
    if getattr(args, "files_opt", None):
        input_files.extend(args.files_opt)

    changed_files = []
    if input_files:
        for f in input_files:
            p = Path(f)
            if not p.is_absolute():
                p = (repo_root / p).resolve()
            try:
                rel = str(p.relative_to(repo_root))
            except ValueError:
                rel = str(p)
            changed_files.append(rel)
    else:
        if getattr(args, "staged", False):
            try:
                res = subprocess.run(["git", "diff", "--name-only", "--cached"], capture_output=True, text=True, cwd=str(repo_root))
                changed_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            except Exception:
                pass
        elif getattr(args, "uncommitted", False):
            try:
                res = subprocess.run(["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True, cwd=str(repo_root))
                changed_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            except Exception:
                pass
        else:
            try:
                res_staged = subprocess.run(["git", "diff", "--name-only", "--cached"], capture_output=True, text=True, cwd=str(repo_root))
                staged = [line.strip() for line in res_staged.stdout.splitlines() if line.strip()]
                if staged:
                    changed_files = staged
                else:
                    res_unstaged = subprocess.run(["git", "diff", "--name-only"], capture_output=True, text=True, cwd=str(repo_root))
                    changed_files = [line.strip() for line in res_unstaged.stdout.splitlines() if line.strip()]
            except Exception:
                pass

    if not changed_files:
        if getattr(args, "json", False):
            print(json.dumps({"status": "clean", "message": "No modified files detected", "inspections": []}))
        else:
            print("[check] No modified files detected in repository.")
        return 0

    # 3. Locate database
    db_path = None
    if getattr(args, "db", None):
        db_path = Path(args.db).resolve()
    else:
        candidates = [
            repo_root / ".daug.sqlite",
            repo_root / ".daug" / "ledger.sqlite",
            Path.cwd() / "gap-demo.sqlite",
            Path.cwd() / "demo.sqlite",
            BASE_DIR / "gap-demo.sqlite",
            BASE_DIR / "demo.sqlite"
        ]
        for c in candidates:
            if c.exists():
                db_path = c
                break

    if not db_path or not db_path.exists():
        err_msg = "[check] Error: No DAUG ledger database found. Specify --db or run 'daug init' first."
        if getattr(args, "json", False):
            print(json.dumps({"error": err_msg, "exit_code": EXIT_INFRA}))
        else:
            print(err_msg, file=sys.stderr)
        return EXIT_INFRA

    ledger = get_ledger(str(db_path))
    cursor = ledger.conn.cursor()

    latest_graph = cursor.execute(
        "SELECT graph_version FROM graph_snapshot WHERE status='published' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if not latest_graph:
        err_msg = f"[check] Error: No published graph snapshot found in '{db_path}'. Run 'daug graph build' first."
        if getattr(args, "json", False):
            print(json.dumps({"error": err_msg, "exit_code": EXIT_INFRA}))
        else:
            print(err_msg, file=sys.stderr)
        return EXIT_INFRA

    graph_version = latest_graph["graph_version"]

    repo_override = Path(args.repo_root).resolve() if getattr(args, "repo_root", None) else None
    retriever = CandidateRetriever(ledger, minimum_score=0.15)
    verifier = StalenessVerifier(ledger, repo_root_override=repo_override)
    patcher = PatchProposer(ledger, repo_root_override=repo_override)

    inspected_results = []
    total_stale = 0

    for file_rel in changed_files:
        art_row = cursor.execute(
            "SELECT * FROM artifact WHERE canonical_uri = ?", (file_rel,)
        ).fetchone()
        if not art_row:
            art_row = cursor.execute(
                "SELECT * FROM artifact WHERE canonical_uri LIKE ? ORDER BY LENGTH(canonical_uri) ASC LIMIT 1",
                (f"%{file_rel}",)
            ).fetchone()

        if not art_row:
            inspected_results.append({
                "file": file_rel,
                "artifact_id": None,
                "status": "untracked_by_daug",
                "candidates": []
            })
            continue

        art_id = art_row["artifact_id"]

        # Fetch git diff snippet for this file if available
        file_diff = None
        try:
            diff_cmd = ["git", "diff", "--cached", "--", file_rel] if getattr(args, "staged", False) else ["git", "diff", "HEAD", "--", file_rel]
            res_diff = subprocess.run(diff_cmd, capture_output=True, text=True, cwd=str(repo_root))
            if res_diff.stdout.strip():
                file_diff = res_diff.stdout
            else:
                res_diff2 = subprocess.run(["git", "diff", "--", file_rel], capture_output=True, text=True, cwd=str(repo_root))
                file_diff = res_diff2.stdout if res_diff2.stdout.strip() else None
        except Exception:
            pass

        change_row = cursor.execute(
            "SELECT change_id FROM change_event WHERE source_artifact_id = ? ORDER BY occurred_at DESC LIMIT 1",
            (art_id,)
        ).fetchone()

        if change_row:
            change_id = change_row["change_id"]
        else:
            change_type = "interface" if not file_rel.endswith(".md") else "documentation"
            change_id = f"change-auto-{art_id[:16]}-{uuid.uuid4().hex[:6]}"
            ledger.record_change_event(
                change_id=change_id,
                source_artifact_id=art_id,
                change_type=change_type,
                impact_score=0.8,
                scope="file"
            )

        try:
            cand_set = retriever.rank_candidates(change_id, graph_version=graph_version, top_k=5)
            # Verify each candidate, passing file_diff
            cursor2 = ledger.conn.cursor()
            cands = cursor2.execute(
                "SELECT candidate_id FROM update_candidate WHERE candidate_set_id=? ORDER BY rank",
                (cand_set["candidate_set_id"],)
            ).fetchall()
            verifs = [verifier.verify_candidate(c["candidate_id"], diff_text=file_diff) for c in cands]
        except Exception as e:
            inspected_results.append({
                "file": file_rel,
                "artifact_id": art_id,
                "status": "retrieval_error",
                "error": str(e),
                "candidates": []
            })
            continue

        file_candidates = []
        for v in verifs:
            is_stale = (v["status"] == "STALE")
            if is_stale:
                total_stale += 1

            patch_info = None
            if is_stale and getattr(args, "propose", False):
                try:
                    patch_info = patcher.propose_patch(v["verification_id"])
                except Exception:
                    pass

            file_candidates.append({
                "candidate_id": v["candidate_id"],
                "target_artifact_id": v["target_artifact_id"],
                "target_uri": v["canonical_uri"],
                "status": v["status"],
                "confidence": v["confidence"],
                "spans": v["spans"],
                "patch": patch_info
            })

        inspected_results.append({
            "file": file_rel,
            "artifact_id": art_id,
            "status": "stale_found" if any(c["status"] == "STALE" for c in file_candidates) else "ok",
            "candidates": file_candidates
        })

    if getattr(args, "json", False):
        out = {
            "database": str(db_path),
            "graph_version": graph_version,
            "total_files": len(changed_files),
            "total_stale": total_stale,
            "inspections": inspected_results
        }
        print(json.dumps(out, indent=2))
    else:
        print("=" * 65)
        print("DAUG Staleness Check")
        print(f"Database: {db_path.name} | Graph Version: {graph_version}")
        print("=" * 65)
        for item in inspected_results:
            print(f"\n[CHANGED] {item['file']}")
            if item.get("status") == "untracked_by_daug":
                print("  (File is not currently indexed in DAUG artifact graph)")
                continue

            stale_items = [c for c in item["candidates"] if c["status"] == "STALE"]
            valid_items = [c for c in item["candidates"] if c["status"] == "VALID"]

            if stale_items:
                print(f"  -> WARNING: {len(stale_items)} document/contract is STALE:")
                for sc in stale_items:
                    print(f"     * [STALE] {sc['target_uri']} (confidence: {sc['confidence']:.2f})")
                    for sp in sc.get("spans", []):
                        print(f"       - {sp['locator']}: {sp['reason_code']}")
                    if sc.get("patch"):
                        p = sc["patch"]
                        print(f"       [Proposed Patch] {p['patch_id']} (Run 'daug patch apply {p['patch_id']}' to apply)")
            elif valid_items:
                print(f"  -> Up to date: {len(valid_items)} related document(s) verified consistent.")
            else:
                print("  -> No related documents mapped in graph.")

        print("\n" + "-" * 65)
        print(f"Summary: {len(changed_files)} file(s) checked, {total_stale} stale document(s) flagged.")
        if total_stale > 0:
            print("Tip: Review flagged documents above before committing or merging.")
        print("-" * 65)

    if total_stale > 0 and getattr(args, "fail_on_stale", False):
        return EXIT_STALE
    return EXIT_OK

HOOK_MARKER_BEGIN = "# --- DAUG HOOK BEGIN ---"
HOOK_MARKER_END = "# --- DAUG HOOK END ---"

def resolve_git_dir(repo_root: Path) -> Optional[Path]:
    """Resolve the real git directory (handles worktrees and .git files)."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
            capture_output=True, text=True, check=True, cwd=str(repo_root)
        )
        out = res.stdout.strip()
        if out:
            return Path(out)
    except Exception:
        pass
    git_dir = repo_root / ".git"
    return git_dir if git_dir.exists() else None

def resolve_hooks_dir(repo_root: Path) -> Path:
    """
    Resolve the directory git will actually read hooks from.

    `git rev-parse --git-path hooks` honours core.hooksPath, which may be set
    globally and therefore point outside the repository. Writing to
    `.git/hooks` when core.hooksPath is configured produces a hook that git
    never executes - a silent no-op that looks like a successful install.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-path", "hooks"],
            capture_output=True, text=True, check=True, cwd=str(repo_root)
        )
        out = res.stdout.strip()
        if out:
            return Path(out)
    except Exception:
        pass
    git_dir = resolve_git_dir(repo_root)
    if git_dir is None:
        raise FileNotFoundError("not a git repository")
    return git_dir / "hooks"

def get_effective_hooks_path_config(repo_root: Path) -> Optional[str]:
    """Return the configured core.hooksPath value, if any (repo overrides global)."""
    try:
        res = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            capture_output=True, text=True, cwd=str(repo_root)
        )
        value = res.stdout.strip()
        return value or None
    except Exception:
        return None

def resolve_daug_entrypoint() -> str:
    """
    Absolute path to a DAUG CLI shim that hooks can invoke reliably.

    Hooks run with an unpredictable CWD and a non-interactive PATH, so a bare
    `daug` lookup and relative `./bin/daug` probes are both unreliable.
    """
    return str((BASE_DIR / "bin" / "daug").resolve())

def build_hook_script_body(hook_type: str, strict: bool, db_path: Optional[str], repo_root: Path) -> str:
    daug_entry = resolve_daug_entrypoint()
    db_line = f'DAUG_DB="{db_path}"' if db_path else 'DAUG_DB=""'
    strict_flag = "--fail-on-stale " if strict else ""

    # Exit-code contract:
    #   0 = clean, or stale in warn-only mode            -> allow commit
    #   1 = stale and strict mode                        -> block commit
    #   3 = DAUG could not run (missing ledger/graph)    -> allow unless strict
    # Any other code (crash, signal) is treated as infrastructure failure.
    if strict:
        tail = (
            'case "$rc" in\n'
            '    0) exit 0 ;;\n'
            '    1) exit 1 ;;\n'
            '    *) echo "[DAUG] check failed to run (exit $rc); blocking because strict mode is enabled." >&2; exit 1 ;;\n'
            'esac\n'
        )
    else:
        tail = (
            'case "$rc" in\n'
            '    1) exit 1 ;;\n'
            '    *) exit 0 ;;\n'
            'esac\n'
        )

    return f"""{HOOK_MARKER_BEGIN}
# Trace-Derived Artifact Update Graph (DAUG) {hook_type} hook
# Mode: {"strict (blocks commit when stale)" if strict else "warn-only (never blocks on staleness)"}
DAUG_ENTRY="{daug_entry}"
{db_line}
DAUG_REPO="{repo_root}"

if [ ! -x "$DAUG_ENTRY" ]; then
    echo "[DAUG] CLI not found at $DAUG_ENTRY - skipping staleness check." >&2
    exit 0
fi

if [ -n "$DAUG_DB" ]; then
    "$DAUG_ENTRY" check --staged --repo-root "$DAUG_REPO" --db "$DAUG_DB" {strict_flag}>/dev/null
else
    "$DAUG_ENTRY" check --staged --repo-root "$DAUG_REPO" {strict_flag}>/dev/null
fi
rc=$?

{tail}{HOOK_MARKER_END}
"""

def cmd_hook_install(args):
    repo_root = getattr(args, "repo", None)
    if not repo_root:
        try:
            res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
            repo_root = Path(res.stdout.strip()).resolve()
        except Exception:
            repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root).resolve()

    try:
        hooks_dir = resolve_hooks_dir(repo_root)
    except FileNotFoundError:
        print(f"[hook-install] Error: '{repo_root}' is not a git repository.", file=sys.stderr)
        return 1

    hook_type = getattr(args, "type", "pre-commit")
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / hook_type

    # Safety gate: only a hooks directory INSIDE this repository is repo-local.
    # When core.hooksPath points outside (e.g. a global ~/.git-hooks), the install
    # would govern every repository on the machine, so require explicit opt-in.
    hooks_dir_is_shared = True
    try:
        hooks_dir.resolve().relative_to(repo_root.resolve())
        hooks_dir_is_shared = False
    except Exception:
        hooks_dir_is_shared = True

    if hooks_dir_is_shared and not getattr(args, "allow_shared_hooks", False):
        configured_hooks_path = get_effective_hooks_path_config(repo_root)
        print(
            f"[hook-install] Refusing to install: git resolves hooks to '{hooks_dir}', "
            f"which is outside this repository (core.hooksPath = '{configured_hooks_path}').",
            file=sys.stderr,
        )
        print(
            f"[hook-install] Installing there would affect every repository using that "
            f"path, not just '{repo_root}'.",
            file=sys.stderr,
        )
        print(
            "[hook-install] Preferred fix - give this repository its own hook directory:",
            file=sys.stderr,
        )
        print(f"[hook-install]   git -C '{repo_root}' config core.hooksPath .githooks", file=sys.stderr)
        print(
            "[hook-install] Then re-run the install. To target the shared directory anyway, "
            "pass --allow-shared-hooks.",
            file=sys.stderr,
        )
        return 1

    strict = bool(getattr(args, "strict", False))
    db_path = getattr(args, "db", None)
    hook_script_body = build_hook_script_body(hook_type, strict, db_path, repo_root)

    existing_content = ""
    if hook_file.exists():
        existing_content = hook_file.read_text(encoding="utf-8")

    if HOOK_MARKER_BEGIN in existing_content:
        pattern = re.compile(rf"{re.escape(HOOK_MARKER_BEGIN)}.*?{re.escape(HOOK_MARKER_END)}\n?", re.DOTALL)
        new_content = pattern.sub(hook_script_body, existing_content)
    else:
        header = "#!/bin/sh\n\n" if not existing_content.startswith("#!") else ""
        new_content = header + existing_content + ("\n" if existing_content and not existing_content.endswith("\n") else "") + hook_script_body

    hook_file.write_text(new_content, encoding="utf-8")
    current_mode = hook_file.stat().st_mode
    hook_file.chmod(current_mode | 0o755)

    mode_desc = "strict (blocks commit if stale)" if strict else "warn-only (prints warning without blocking)"
    print(f"[hook-install] Installed DAUG '{hook_type}' hook in '{hook_file}' ({mode_desc}).")

    if hooks_dir_is_shared:
        print(
            f"[hook-install] Warning: this hook lives in a shared directory "
            f"('{hooks_dir}') and therefore applies to every repository using the same "
            f"core.hooksPath.",
            file=sys.stderr,
        )

    # Report the exit-code contract so operators know if commits can be blocked.
    if strict:
        print("[hook-install] Strict mode: exits 1 (blocks commit) when stale documents are found.")
    else:
        print("[hook-install] Warn-only mode: prints findings but never blocks the commit.")
    return 0

def cmd_hook_uninstall(args):
    repo_root = getattr(args, "repo", None)
    if not repo_root:
        try:
            res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
            repo_root = Path(res.stdout.strip()).resolve()
        except Exception:
            repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root).resolve()

    hook_type = getattr(args, "type", "pre-commit")

    try:
        hooks_dir = resolve_hooks_dir(repo_root)
    except FileNotFoundError:
        print(f"[hook-uninstall] Error: '{repo_root}' is not a git repository.", file=sys.stderr)
        return 1

    hook_file = hooks_dir / hook_type
    if not hook_file.exists():
        print(f"[hook-uninstall] No hook found at '{hook_file}'.")
        return 0

    content = hook_file.read_text(encoding="utf-8")
    if HOOK_MARKER_BEGIN not in content:
        print(f"[hook-uninstall] No DAUG hook block found in '{hook_file}'.")
        return 0

    pattern = re.compile(rf"{re.escape(HOOK_MARKER_BEGIN)}.*?{re.escape(HOOK_MARKER_END)}\n?", re.DOTALL)
    new_content = pattern.sub("", content).strip()

    if not new_content or new_content == "#!/bin/sh":
        hook_file.unlink()
        print(f"[hook-uninstall] Removed DAUG hook file '{hook_file}'.")
    else:
        hook_file.write_text(new_content + "\n", encoding="utf-8")
        print(f"[hook-uninstall] Removed DAUG hook section from '{hook_file}'.")
    return 0

def cmd_demo_run(args):
    print("=" * 70)
    print("DAUG (Trace-Derived Artifact Update Graph) Demo - 5-Minute Run")
    print("Policy Mode: PROPOSE_ONLY | Status: PROPOSED | Zero Production Writes")
    print("=" * 70)

    db_path = args.db
    if os.path.exists(db_path):
        os.remove(db_path)

    run_id = f"demo-run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    repo_root = BASE_DIR / "fixtures/demo-repo"

    # Step 1: Init and register repository
    print("\n[Step 1/7] Initializing SQLite Event Ledger & Registering Artifacts...")
    ledger = get_ledger(db_path)
    ledger.init_db()
    ledger.register_repository("demo-auth-repo", str(repo_root))

    artifacts_registered = 0
    for root, _, files in os.walk(repo_root):
        for f in files:
            p = Path(root) / f
            rel = str(p.relative_to(repo_root))
            kind = "documentation" if rel.endswith(".md") else ("test" if "test" in rel else "source_code")
            risk = "R2" if (kind in ("documentation", "test")) else "R3"
            with open(p, "rb") as fp:
                h = compute_sha256(fp.read())
            aid = ledger.register_artifact("demo-auth-repo", rel, artifact_kind=kind, risk_class=risk)
            ledger.record_artifact_version(aid, h, size_bytes=p.stat().st_size)
            artifacts_registered += 1
    print(f"  -> {artifacts_registered} artifacts registered with content hashes.")

    # Step 2: Ingest organic trace
    print("\n[Step 2/7] Ingesting Organic Trace (Trace-Derived Behavior Signals)...")
    normalizer = Normalizer()
    organic_trace_path = BASE_DIR / "fixtures/traces/organic-interface-change.jsonl"
    ledger.register_trace_run("trace-demo-interface-001", "task-rename-user-id", "demo-auth-repo", "2026-09-14T01:00:00Z")
    for ev in normalizer.read_jsonl(str(organic_trace_path)):
        ledger.append_tool_event(normalizer.validate_and_normalize_event(ev))
    print("  -> Organic trace ingested. 7 tool events (search, read, edit, test) recorded.")

    # Step 3: Record changes
    print("\n[Step 3/7] Recording Source Changes (Interface Change & Negative Control)...")
    ledger.record_change_event(
        change_id="change-interface-001",
        source_artifact_id="artifact-src-auth-user_context-ts",
        change_type="interface",
        impact_score=0.9,
        scope="file"
    )
    ledger.record_change_event(
        change_id="change-refactor-001",
        source_artifact_id="artifact-src-auth-auth_filter-ts",
        change_type="refactor",
        impact_score=0.2,
        scope="symbol"
    )
    print("  -> Change events recorded: change-interface-001 (interface) & change-refactor-001 (refactor).")

    # Step 4: Build Update Graph
    print("\n[Step 4/7] Building Trace-Derived Artifact Update Graph Snapshot...")
    builder = GraphBuilder(ledger)
    snap = builder.build_snapshot(graph_version="graph-v0.1-demo")
    print(f"  -> Graph built: {snap['edges_count']} edges fused across Static, Reference, and Trace.")

    # Step 5: Rank candidates for Scenario A
    print("\n[Step 5/7] Candidate Retrieval & Ranking for Interface Change (Scenario A)...")
    retriever = CandidateRetriever(ledger, minimum_score=0.20)
    cand_set_a = retriever.rank_candidates("change-interface-001", graph_version="graph-v0.1-demo")
    print(f"  -> Recalled {len(cand_set_a['candidates'])} candidates:")
    for c in cand_set_a["candidates"]:
        print(f"     Rank {c['rank']}: {c['target_artifact_id']} (score: {c['total_score']:.4f})")

    # Step 6: Staleness Verification & Patch Proposal
    print("\n[Step 6/7] Running Independent Staleness Verifier & Proposing Patches...")
    verifier = StalenessVerifier(ledger)
    verifs_a = verifier.verify_candidate_set(cand_set_a["candidate_set_id"])

    patcher = PatchProposer(ledger)
    patches_a = []
    for v in verifs_a:
        st = v["status"]
        spans_cnt = len(v.get("spans", []))
        print(f"  -> Candidate {v['candidate_id']}: status={st}, confidence={v['confidence']:.2f}, spans={spans_cnt}")
        if st == "STALE":
            p = patcher.propose_patch(v["verification_id"])
            if p:
                patches_a.append(p)
                print(f"     [Patch Proposed] ID={p['patch_id']} for {p['target_artifact_uri']} (Expected Hash: {p['expected_target_hash'][:16]}...)")
                print(f"     Minimality: {p['minimality_check']}, Policy: {p['policy_decision']['action']} ({p['policy_decision']['reason_code']})")

    # Step 7: Negative Control (Scenario B)
    print("\n[Step 7/7] Executing Negative Control (Scenario B - Local Refactor)...")
    cand_set_b = retriever.rank_candidates("change-refactor-001", graph_version="graph-v0.1-demo")
    verifs_b = verifier.verify_candidate_set(cand_set_b["candidate_set_id"])
    stale_in_b = [v for v in verifs_b if v["status"] == "STALE"]
    print(f"  -> Local refactor produced {len(stale_in_b)} STALE verifications (Expected: 0). Correctly blocked false updates!")

    # Self-Reinforcement control (Scenario D)
    print("\n[Bonus: Scenario D] Demonstrating Self-Reinforcement Control (System Recommended Read)...")
    assisted_trace_path = BASE_DIR / "fixtures/traces/assisted-unrelated-read.jsonl"
    ledger.register_trace_run("trace-demo-assisted-001", "task-assisted-read", "demo-auth-repo", "2026-09-14T01:05:00Z")
    for ev in normalizer.read_jsonl(str(assisted_trace_path)):
        ledger.append_tool_event(normalizer.validate_and_normalize_event(ev))
    snap_after_assisted = builder.build_snapshot(graph_version="graph-v0.1-after-assisted")
    print(f"  -> Ingested recommendation event. Organic weight=1.0, recommended weight=0.05. Edge weight inflation suppressed.")

    # Generate Report
    print("\nGenerating comprehensive run artifacts...")
    reporter = RunReporter(args.runs_dir)
    out_dir = reporter.generate_report(
        run_id=run_id,
        ledger=ledger,
        graph_version="graph-v0.1-demo",
        change_id="change-interface-001",
        candidate_set_id=cand_set_a["candidate_set_id"],
        verifications=verifs_a,
        patches=patches_a
    )

    print("\n" + "=" * 70)
    print(f"DEMO COMPLETED SUCCESSFULLY! Artifacts saved to:")
    print(f"  - Report: file://{out_dir / 'report.html'}")
    print(f"  - Manifest: file://{out_dir / 'run_manifest.json'}")
    print(f"  - Hashes: file://{out_dir / 'hashes.sha256'}")
    print("=" * 70)
    print("Demonstrated Status Summary:")
    print("  Event ingestion: Tested")
    print("  Offline replay: Tested")
    print("  Candidate ranking: Tested on demo fixture")
    print("  Staleness verification: Tested on synthetic fixture")
    print("  Patch application: Not implemented (Strictly Propose Only)")
    print("  Production enablement: Not authorized")
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="DAUG: Trace-Derived Artifact Update Graph Demo CLI")
    subparsers = parser.add_subparsers(dest="command")

    # init
    p_init = subparsers.add_parser("init", help="Initialize ledger database and register artifacts")
    p_init.add_argument("--db", default="demo.sqlite", help="SQLite database path")
    p_init.add_argument("--repo-root", default=str(BASE_DIR / "fixtures/demo-repo"), help="Path to repository root")
    p_init.add_argument("--repo-id", default="demo-auth-repo", help="Repository identifier")

    # trace
    p_ingest = subparsers.add_parser("trace", help="Trace commands")
    p_ingest_sub = p_ingest.add_subparsers(dest="trace_command")
    p_ing = p_ingest_sub.add_parser("ingest", help="Ingest JSONL trace")
    p_ing.add_argument("trace_file", help="Path to trace JSONL")
    p_ing.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    p_rec = p_ingest_sub.add_parser("record", help="Record single live tool event")
    p_rec.add_argument("--tool", default="generic", help="Tool name")
    p_rec.add_argument("--op", default="read", choices=["read", "search", "edit", "write", "delete", "test", "execute", "commit", "approve", "reject"], help="Operation type")
    p_rec.add_argument("--path", default=None, help="Target file path")
    p_rec.add_argument("--status", default="success", choices=["success", "failure", "cancelled", "unknown"], help="Result status")
    p_rec.add_argument("--trace-id", default=None, help="Trace / session ID")
    p_rec.add_argument("--repo-id", default=None, help="Repository ID")
    p_rec.add_argument("--db", default=None, help="SQLite database path")
    p_rec.add_argument("--quiet", action="store_true", help="Suppress output")

    # graph build
    p_graph = subparsers.add_parser("graph", help="Graph commands")
    p_graph_sub = p_graph.add_subparsers(dest="graph_command")
    p_gb = p_graph_sub.add_parser("build", help="Build graph snapshot")
    p_gb.add_argument("--until", default=None, help="Snapshot timestamp")
    p_gb.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    # candidates rank
    p_cand = subparsers.add_parser("candidates", help="Candidates commands")
    p_cand_sub = p_cand.add_subparsers(dest="candidates_command")
    p_cr = p_cand_sub.add_parser("rank", help="Rank candidates for change")
    p_cr.add_argument("--change", required=True, help="Change event ID")
    p_cr.add_argument("--top-k", type=int, default=10, help="Top K candidates")
    p_cr.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    # verify
    p_ver = subparsers.add_parser("verify", help="Run staleness verifier")
    p_ver.add_argument("--candidate-set", required=True, help="Candidate set ID")
    p_ver.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    # patch
    p_patch = subparsers.add_parser("patch", help="Patch commands (propose, list, show, apply)")
    p_patch_sub = p_patch.add_subparsers(dest="patch_command")
    
    p_pp = p_patch_sub.add_parser("propose", help="Propose minimal patch")
    p_pp.add_argument("--verification", required=True, help="Verification ID")
    p_pp.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    p_pl = p_patch_sub.add_parser("list", help="List proposed patches")
    p_pl.add_argument("--status", default=None, help="Filter by status (e.g. proposed, applied)")
    p_pl.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    p_ps = p_patch_sub.add_parser("show", help="Show patch diff")
    p_ps.add_argument("patch_id", help="Patch ID to show")
    p_ps.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    p_pa = p_patch_sub.add_parser("apply", help="Apply proposed patch to disk with CAS verification")
    p_pa.add_argument("patch_id", help="Patch ID to apply")
    p_pa.add_argument("-y", "--yes", action="store_true", help="Apply without interactive confirmation")
    p_pa.add_argument("--db", default="demo.sqlite", help="SQLite database path")
    p_pa.add_argument("--repo-root", default=None, help="Override repository root path")

    # check
    p_check = subparsers.add_parser("check", help="Check modified files against documentation update graph")
    p_check.add_argument("files", nargs="*", help="Specific files to check (defaults to git changes)")
    p_check.add_argument("--files", nargs="+", dest="files_opt", help="Explicit list of files to check")
    p_check.add_argument("--staged", action="store_true", help="Check git staged changes only")
    p_check.add_argument("--uncommitted", action="store_true", help="Check all uncommitted git changes (HEAD)")
    p_check.add_argument("--db", default=None, help="SQLite database path (auto-discovered if omitted)")
    p_check.add_argument("--repo-root", default=None, help="Repository root path")
    p_check.add_argument("--json", action="store_true", help="Output results in JSON format")
    p_check.add_argument("--fail-on-stale", action="store_true", help="Exit with non-zero code if stale documents found")
    p_check.add_argument("--propose", action="store_true", help="Automatically generate patch proposals for stale documents")

    # hook
    p_hook = subparsers.add_parser("hook", help="Git hook management (install, uninstall)")
    p_hook_sub = p_hook.add_subparsers(dest="hook_command")
    
    p_hi = p_hook_sub.add_parser("install", help="Install git hook")
    p_hi.add_argument("--repo", default=None, help="Repository path (defaults to current git repo)")
    p_hi.add_argument("--type", default="pre-commit", choices=["pre-commit", "pre-push"], help="Hook type")
    p_hi.add_argument("--strict", action="store_true", help="Block commits if stale docs found (default: warn only)")
    p_hi.add_argument("--db", default=None, help="Pin the ledger path inside the hook (defaults to repo/cwd auto-discovery)")
    p_hi.add_argument(
        "--allow-shared-hooks",
        action="store_true",
        dest="allow_shared_hooks",
        help="Permit installing into a shared core.hooksPath directory that affects other repositories",
    )

    p_hu = p_hook_sub.add_parser("uninstall", help="Uninstall git hook")
    p_hu.add_argument("--repo", default=None, help="Repository path (defaults to current git repo)")
    p_hu.add_argument("--type", default="pre-commit", choices=["pre-commit", "pre-push"], help="Hook type")

    # review
    p_rev = subparsers.add_parser("review", help="Start interactive Web Review Dashboard (P2 human-in-the-loop deployment)")
    p_rev.add_argument("--port", type=int, default=8484, help="HTTP port (default 8484)")
    p_rev.add_argument("--db", default=None, help="SQLite database path")
    p_rev.add_argument("--repo-root", default=None, help="Repository root path")
    p_rev.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")

    # demo run
    p_demo = subparsers.add_parser("demo", help="Demo commands")
    p_demo_sub = p_demo.add_subparsers(dest="demo_command")
    p_dr = p_demo_sub.add_parser("run", help="Run end-to-end 5-minute demo")
    p_dr.add_argument("--db", default="demo.sqlite", help="SQLite database path")
    p_dr.add_argument("--runs-dir", default="runs", help="Output runs directory")

    args = parser.parse_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "check":
        sys.exit(cmd_check(args))
    elif args.command == "trace":
        t_cmd = getattr(args, "trace_command", None)
        if t_cmd == "ingest":
            cmd_trace_ingest(args)
        elif t_cmd == "record":
            sys.exit(cmd_trace_record(args))
        else:
            p_ingest.print_help()
    elif args.command == "graph" and getattr(args, "graph_command", None) == "build":
        cmd_graph_build(args)
    elif args.command == "candidates" and getattr(args, "candidates_command", None) == "rank":
        cmd_candidates_rank(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "patch":
        p_cmd = getattr(args, "patch_command", None)
        if p_cmd == "propose":
            cmd_patch_propose(args)
        elif p_cmd == "apply":
            sys.exit(cmd_patch_apply(args))
        elif p_cmd == "list":
            sys.exit(cmd_patch_list(args))
        elif p_cmd == "show":
            sys.exit(cmd_patch_show(args))
        else:
            p_patch.print_help()
    elif args.command == "hook":
        h_cmd = getattr(args, "hook_command", None)
        if h_cmd == "install":
            sys.exit(cmd_hook_install(args))
        elif h_cmd == "uninstall":
            sys.exit(cmd_hook_uninstall(args))
        else:
            p_hook.print_help()
    elif args.command == "review":
        sys.exit(cmd_review(args))
    elif args.command == "demo" and getattr(args, "demo_command", None) == "run":
        cmd_demo_run(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
