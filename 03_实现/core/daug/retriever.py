import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from daug.ledger import Ledger, compute_json_digest, compute_str_digest, current_iso

class CandidateRetriever:
    def __init__(self, ledger: Ledger, minimum_score: float = 0.20):
        self.ledger = ledger
        self.minimum_score = minimum_score

    def rank_candidates(
        self,
        change_id: str,
        graph_version: Optional[str] = None,
        top_k: int = 10,
        policy_version: str = "daug.policy.v1"
    ) -> Dict[str, Any]:
        cursor = self.ledger.conn.cursor()

        # 1. Look up change event
        change = cursor.execute("SELECT * FROM change_event WHERE change_id=?", (change_id,)).fetchone()
        if not change:
            raise ValueError(f"Change event '{change_id}' not found in ledger")

        source_artifact_id = change["source_artifact_id"]
        change_type = change["change_type"]

        # 2. Look up graph version
        if not graph_version:
            latest_graph = cursor.execute(
                "SELECT graph_version FROM graph_snapshot WHERE status='published' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if not latest_graph:
                raise ValueError("No published graph snapshot found. Build graph first.")
            graph_version = latest_graph["graph_version"]

        # 3. Retrieve edges originating from source_artifact_id
        edges = cursor.execute(
            """
            SELECT * FROM graph_edge
            WHERE graph_version=? AND source_artifact_id=?
            """,
            (graph_version, source_artifact_id)
        ).fetchall()

        # Aggregate by target_artifact_id
        target_candidates: Dict[str, Dict[str, Any]] = {}
        for edge in edges:
            tgt_id = edge["target_artifact_id"]
            if tgt_id not in target_candidates:
                target_candidates[tgt_id] = {
                    "target_artifact_id": tgt_id,
                    "relations": {},
                    "evidences": [],
                    "total_score": 0.0,
                    "organic_support": 0.0,
                    "recommended_support": 0.0
                }

            rel = edge["relation_type"]
            score = edge["score"]
            target_candidates[tgt_id]["relations"][rel] = score
            target_candidates[tgt_id]["organic_support"] += edge["organic_support"]
            target_candidates[tgt_id]["recommended_support"] += edge["recommended_support"]

            # Fetch edge evidences
            ev_rows = cursor.execute(
                "SELECT * FROM edge_evidence WHERE edge_id=?", (edge["edge_id"],)
            ).fetchall()
            for ev in ev_rows:
                target_candidates[tgt_id]["evidences"].append(dict(ev))

        # 4. Compute composite fused score for each candidate
        ranked_list = []
        for tgt_id, info in target_candidates.items():
            # Relation-type calibrated weighting based on change_type
            # For interface and schema changes, explicit references (contracts, docs) have elevated weight
            rel_weights = {"trace": 1.0, "reference": 1.0, "static": 1.0}
            if change_type in ("interface", "schema"):
                rel_weights["reference"] = 1.25
                rel_weights["static"] = 0.85
            elif change_type == "refactor":
                rel_weights["static"] = 1.1
                rel_weights["reference"] = 0.5

            # Multimodal fusion: weighted probabilistic union
            prod_complement = 1.0
            for rel, s in info["relations"].items():
                w = rel_weights.get(rel, 1.0)
                effective_s = min(0.999, s * w)
                prod_complement *= (1.0 - effective_s)
            fused_score = round(1.0 - prod_complement, 4)

            # Sub-linear evidence support contribution for tie-breaking
            # log1p dampens repetitive test loop noise while preserving genuine signal
            damped_support = math.log1p(info["organic_support"])

            art = cursor.execute("SELECT canonical_uri FROM artifact WHERE artifact_id=?", (tgt_id,)).fetchone()
            canonical_uri = art["canonical_uri"] if art else ""

            # Negative control check: If change_type is 'refactor' and target is documentation,
            # documentation score should not trigger staleness update
            if change_type == "refactor":
                if "docs/" in canonical_uri or canonical_uri.endswith(".md"):
                    fused_score = round(fused_score * 0.1, 4)
            elif change_type in ("interface", "schema", "behavior"):
                # Cross-modal boost for specifications, contracts, and documentation
                if canonical_uri.endswith((".md", ".markdown", ".json", ".yaml", ".yml")):
                    fused_score = min(1.0, round(fused_score * 1.08, 4))
                    damped_support *= 1.35

            if fused_score >= self.minimum_score:
                info["total_score"] = fused_score
                info["rank_key"] = (fused_score, round(damped_support, 4))
                ranked_list.append(info)

        # Sort descending by composite rank key
        ranked_list.sort(key=lambda x: x["rank_key"], reverse=True)
        ranked_list = ranked_list[:top_k]

        # 5. Insert candidate_set and update_candidate records into DB
        now = current_iso()
        candidate_set_id = f"candset-{change_id}-{graph_version[:16]}"
        retrieval_config_digest = compute_json_digest({
            "minimum_score": self.minimum_score,
            "top_k": top_k,
            "policy_version": policy_version
        })
        candidate_set_digest = compute_json_digest([
            {"target": c["target_artifact_id"], "score": c["total_score"]}
            for c in ranked_list
        ])

        with self.ledger.conn:
            self.ledger.conn.execute(
                """
                INSERT INTO candidate_set (
                    candidate_set_id, change_id, graph_version, policy_version,
                    retrieval_config_digest, top_k, candidate_set_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_set_id) DO UPDATE SET
                    candidate_set_digest=excluded.candidate_set_digest
                """,
                (
                    candidate_set_id, change_id, graph_version, policy_version,
                    retrieval_config_digest, top_k, candidate_set_digest, now
                )
            )

            # Check if any verifications exist for this candidate set
            has_verifs = self.ledger.conn.execute(
                """
                SELECT count(*) FROM verification v
                JOIN update_candidate uc ON v.candidate_id = uc.candidate_id
                WHERE uc.candidate_set_id = ?
                """,
                (candidate_set_id,)
            ).fetchone()[0] > 0

            if not has_verifs:
                self.ledger.conn.execute(
                    "DELETE FROM update_candidate WHERE candidate_set_id=?",
                    (candidate_set_id,)
                )
            else:
                # Temporarily offset ranks to avoid UNIQUE(candidate_set_id, rank) collision
                self.ledger.conn.execute(
                    "UPDATE update_candidate SET rank = rank + 1000000 WHERE candidate_set_id=?",
                    (candidate_set_id,)
                )

            for rank_idx, cand in enumerate(ranked_list, start=1):
                cand_id = f"cand-{candidate_set_id}-{rank_idx}"
                feature_digest = compute_json_digest(cand["relations"])
                explanation = {
                    "relations": cand["relations"],
                    "organic_support": cand["organic_support"],
                    "recommended_support": cand["recommended_support"],
                    "evidence_count": len(cand["evidences"])
                }
                explanation_digest = compute_json_digest(explanation)
                trigger_rule = "multi_signal_fusion" if len(cand["relations"]) > 1 else list(cand["relations"].keys())[0]

                self.ledger.conn.execute(
                    """
                    INSERT INTO update_candidate (
                        candidate_id, candidate_set_id, target_artifact_id, rank,
                        score, feature_digest, explanation_digest, trigger_rule
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(candidate_set_id, target_artifact_id) DO UPDATE SET
                        score=excluded.score, rank=excluded.rank
                    """,
                    (
                        cand_id, candidate_set_id, cand["target_artifact_id"], rank_idx,
                        cand["total_score"], feature_digest, explanation_digest, trigger_rule
                    )
                )
                cand["candidate_id"] = cand_id
                cand["rank"] = rank_idx

        return {
            "candidate_set_id": candidate_set_id,
            "change_id": change_id,
            "graph_version": graph_version,
            "candidates": ranked_list
        }
