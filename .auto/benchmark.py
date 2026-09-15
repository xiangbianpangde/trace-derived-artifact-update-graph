import sys
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from daug.ledger import Ledger
from daug.retriever import CandidateRetriever
from daug.verifier import StalenessVerifier

def run_benchmark():
    start_time = time.perf_counter()

    # --- Scenario 1: Demo Auth Interface Change ---
    demo_db = PROJECT_ROOT / "demo.sqlite"
    ledger_demo = Ledger(str(demo_db))
    retriever_demo = CandidateRetriever(ledger_demo)
    res_s1 = retriever_demo.rank_candidates("change-interface-001", top_k=10)
    ranks_s1 = [c["target_artifact_id"] for c in res_s1["candidates"]]

    targets_s1 = ["auth_design", "api_contract"]

    # --- Scenario 2: Real GAP Trace Pager Change ---
    gap_db = PROJECT_ROOT / "gap-demo.sqlite"
    ledger_gap = Ledger(str(gap_db))
    retriever_gap = CandidateRetriever(ledger_gap)
    res_s2 = retriever_gap.rank_candidates("change-real-pager-001", top_k=10)
    ranks_s2 = [c["target_artifact_id"] for c in res_s2["candidates"]]

    targets_s2 = ["09-Pi", "checkpoint.schema", "HANDOFF"]

    # --- Scenario 3: Real GAP Trace Checkpoint Change ---
    res_s3 = retriever_gap.rank_candidates("change-real-checkpoint-001", top_k=10)
    ranks_s3 = [c["target_artifact_id"] for c in res_s3["candidates"]]

    targets_s3 = ["STATUS", "worklog"]

    # --- Negative Control: Scenario B Refactor ---
    res_neg = retriever_demo.rank_candidates("change-refactor-001", top_k=5)
    verifier_demo = StalenessVerifier(ledger_demo)
    verifs_neg = verifier_demo.verify_candidate_set(res_neg["candidate_set_id"])
    stale_neg = [v for v in verifs_neg if v["status"] == "STALE"]
    neg_pass = (len(stale_neg) == 0)

    # Calculate Reciprocal Ranks
    def compute_rr(ranks, targets):
        for i, r in enumerate(ranks, start=1):
            if any(t in r for t in targets):
                return 1.0 / i
        return 0.0

    rr_s1 = compute_rr(ranks_s1, targets_s1)
    rr_s2 = compute_rr(ranks_s2, targets_s2)
    rr_s3 = compute_rr(ranks_s3, targets_s3)

    mrr = (rr_s1 + rr_s2 + rr_s3) / 3.0

    # Calculate Recall@5
    def recall_at_k(ranks, targets, k=5):
        top_k = ranks[:k]
        hit_count = sum(1 for t in targets if any(t in r for r in top_k))
        return hit_count / len(targets) if targets else 0.0

    rec_s1 = recall_at_k(ranks_s1, targets_s1, 5)
    rec_s2 = recall_at_k(ranks_s2, targets_s2, 5)
    rec_s3 = recall_at_k(ranks_s3, targets_s3, 5)
    avg_recall_5 = (rec_s1 + rec_s2 + rec_s3) / 3.0

    # Calculate Precision@3
    def precision_at_k(ranks, targets, k=3):
        top_k = ranks[:k]
        rel_count = sum(1 for r in top_k if any(t in r for t in targets))
        return rel_count / k

    prec_s1 = precision_at_k(ranks_s1, targets_s1, 3)
    prec_s2 = precision_at_k(ranks_s2, targets_s2, 3)
    prec_s3 = precision_at_k(ranks_s3, targets_s3, 3)
    avg_prec_3 = (prec_s1 + prec_s2 + prec_s3) / 3.0

    # Verifier F1 score
    # True positives: s1 detected stale
    verifs_s1 = verifier_demo.verify_candidate_set(res_s1["candidate_set_id"])
    pos_stale = [v for v in verifs_s1 if v["status"] == "STALE"]
    pos_pass = (len(pos_stale) > 0)

    verifier_f1 = 1.0 if (neg_pass and pos_pass) else (0.5 if (neg_pass or pos_pass) else 0.0)

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Output in autoresearch METRIC format
    print(f"METRIC mrr={mrr:.4f}")
    print(f"METRIC recall_at_5={avg_recall_5:.4f}")
    print(f"METRIC precision_at_3={avg_prec_3:.4f}")
    print(f"METRIC verifier_f1={verifier_f1:.4f}")
    print(f"METRIC latency_ms={elapsed_ms:.1f}")

if __name__ == "__main__":
    run_benchmark()
