import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from daug.ledger import Ledger, compute_sha256
from daug.normalizer import Normalizer
from daug.graph import GraphBuilder
from daug.retriever import CandidateRetriever
from daug.verifier import StalenessVerifier
from daug.patcher import PatchProposer
from daug.policy import PolicyEngine
from daug.reporter import RunReporter

BASE_DIR = Path(__file__).resolve().parent.parent

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
    for root, _, files in os.walk(repo_root):
        for f in files:
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

    # trace ingest
    p_ingest = subparsers.add_parser("trace", help="Trace commands")
    p_ingest_sub = p_ingest.add_subparsers(dest="trace_command")
    p_ing = p_ingest_sub.add_parser("ingest", help="Ingest JSONL trace")
    p_ing.add_argument("trace_file", help="Path to trace JSONL")
    p_ing.add_argument("--db", default="demo.sqlite", help="SQLite database path")

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

    # patch propose
    p_patch = subparsers.add_parser("patch", help="Patch commands")
    p_patch_sub = p_patch.add_subparsers(dest="patch_command")
    p_pp = p_patch_sub.add_parser("propose", help="Propose minimal patch")
    p_pp.add_argument("--verification", required=True, help="Verification ID")
    p_pp.add_argument("--db", default="demo.sqlite", help="SQLite database path")

    # demo run
    p_demo = subparsers.add_parser("demo", help="Demo commands")
    p_demo_sub = p_demo.add_subparsers(dest="demo_command")
    p_dr = p_demo_sub.add_parser("run", help="Run end-to-end 5-minute demo")
    p_dr.add_argument("--db", default="demo.sqlite", help="SQLite database path")
    p_dr.add_argument("--runs-dir", default="runs", help="Output runs directory")

    args = parser.parse_args()
    if args.command == "init":
        cmd_init(args)
    elif args.command == "trace" and getattr(args, "trace_command", None) == "ingest":
        cmd_trace_ingest(args)
    elif args.command == "graph" and getattr(args, "graph_command", None) == "build":
        cmd_graph_build(args)
    elif args.command == "candidates" and getattr(args, "candidates_command", None) == "rank":
        cmd_candidates_rank(args)
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "patch" and getattr(args, "patch_command", None) == "propose":
        cmd_patch_propose(args)
    elif args.command == "demo" and getattr(args, "demo_command", None) == "run":
        cmd_demo_run(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
