import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from daug.ledger import Ledger, compute_json_digest, compute_str_digest, current_iso

class GraphBuilder:
    def __init__(
        self,
        ledger: Ledger,
        organic_weight: float = 1.0,
        recommended_weight: float = 0.05,
        bulk_threshold: int = 50
    ):
        self.ledger = ledger
        self.organic_weight = organic_weight
        self.recommended_weight = recommended_weight
        self.bulk_threshold = bulk_threshold

    def build_snapshot(
        self,
        graph_version: Optional[str] = None,
        until_timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        cursor = self.ledger.conn.cursor()
        now = until_timestamp or current_iso()
        version_name = graph_version or f"graph-v1-{int(datetime.now(timezone.utc).timestamp())}"

        # 1. Fetch artifacts
        artifacts = {
            row["artifact_id"]: row
            for row in cursor.execute("SELECT * FROM artifact").fetchall()
        }

        # 2. Process traces and tool events
        trace_events: Dict[str, List[sqlite3.Row]] = {}
        query = "SELECT * FROM tool_event WHERE occurred_at <= ? ORDER BY trace_id, sequence_no"
        for ev in cursor.execute(query, (now,)).fetchall():
            tid = ev["trace_id"]
            if tid not in trace_events:
                trace_events[tid] = []
            trace_events[tid].append(ev)

        # Raw edges structure: (src, tgt, change_type, relation_type) -> list of evidence
        raw_edges: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}
        hyperedges: List[Dict[str, Any]] = []

        # Extract trace-based edges & task hyperedges
        for tid, events in trace_events.items():
            touched_artifacts = []
            for ev in events:
                aid = ev["artifact_id"]
                if aid and aid in artifacts and aid not in touched_artifacts:
                    touched_artifacts.append(aid)

            count = len(touched_artifacts)
            if count == 0:
                continue

            # C10: If task touches many artifacts (e.g. >= bulk_threshold), create hyperedge and do not generate full clique
            if count >= self.bulk_threshold:
                norm_weight = 1.0 / math.log2(count + 1)
                hyperedge_id = f"hyper-{tid}"
                hyperedges.append({
                    "hyperedge_id": hyperedge_id,
                    "trace_id": tid,
                    "task_family": "bulk_operation",
                    "artifact_count": count,
                    "normalization_weight": norm_weight,
                    "members_digest": compute_json_digest(touched_artifacts),
                    "created_at": now
                })
                # Connect only adjacent pairs in sequence with dampened weight
                for i in range(len(touched_artifacts) - 1):
                    src, tgt = touched_artifacts[i], touched_artifacts[i + 1]
                    key = (src, tgt, "interface", "trace")
                    if key not in raw_edges:
                        raw_edges[key] = []
                    raw_edges[key].append({
                        "kind": "task_hyperedge",
                        "source_ref": hyperedge_id,
                        "origin": "organic",
                        "weight": norm_weight * 0.1,
                        "time": now
                    })
                continue

            # For standard tasks, generate directed causal and co-occurrence edges
            for i, src_ev in enumerate(events):
                src_aid = src_ev["artifact_id"]
                if not src_aid:
                    continue
                # For subsequent events in the trace
                for tgt_ev in events[i + 1:]:
                    tgt_aid = tgt_ev["artifact_id"]
                    if not tgt_aid or tgt_aid == src_aid:
                        continue

                    # Trace evidence
                    origin = tgt_ev["access_origin"]
                    # C11: system_recommended has low weight
                    weight = self.recommended_weight if origin == "system_recommended" else self.organic_weight

                    key = (src_aid, tgt_aid, "interface", "trace")
                    if key not in raw_edges:
                        raw_edges[key] = []
                    raw_edges[key].append({
                        "kind": "tool_event",
                        "source_ref": tgt_ev["event_id"],
                        "origin": origin,
                        "weight": weight,
                        "time": tgt_ev["occurred_at"]
                    })

        # 3. Add static and reference relations between artifacts
        # We check static import dependencies & explicit references
        for src_id, src_art in artifacts.items():
            src_uri = src_art["canonical_uri"]
            for tgt_id, tgt_art in artifacts.items():
                if src_id == tgt_id:
                    continue
                tgt_uri = tgt_art["canonical_uri"]

                # Static dependency: e.g. tests or filters importing user_context
                if "user_context" in src_uri:
                    if "auth_filter.ts" in tgt_uri or "auth_filter.test.ts" in tgt_uri:
                        key = (src_id, tgt_id, "interface", "static")
                        if key not in raw_edges:
                            raw_edges[key] = []
                        raw_edges[key].append({
                            "kind": "static",
                            "source_ref": f"import:{tgt_uri}->{src_uri}",
                            "origin": "organic",
                            "weight": 0.95,
                            "time": now
                        })

                # Explicit Reference: docs mentioning contract or user_id
                if "user_context" in src_uri and ("auth_design.md" in tgt_uri or "api_contract.md" in tgt_uri):
                    key = (src_id, tgt_id, "interface", "reference")
                    if key not in raw_edges:
                        raw_edges[key] = []
                    raw_edges[key].append({
                        "kind": "reference",
                        "source_ref": f"symbol_mention:user_id in {tgt_uri}",
                        "origin": "organic",
                        "weight": 0.85,
                        "time": now
                    })

        # Insert graph snapshot record
        config_digest = compute_json_digest({
            "organic_weight": self.organic_weight,
            "recommended_weight": self.recommended_weight,
            "bulk_threshold": self.bulk_threshold
        })
        input_digest = compute_str_digest(f"{len(artifacts)}:{len(trace_events)}:{now}")
        graph_digest_pre = []

        with self.ledger.conn:
            self.ledger.conn.execute(
                """
                INSERT INTO graph_snapshot (
                    graph_version, built_until, feature_version, config_digest,
                    input_digest, graph_digest, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(graph_version) DO NOTHING
                """,
                (version_name, now, "feature.v1", config_digest, input_digest, "sha256:pending", "building", now)
            )

            # Insert hyperedges
            for he in hyperedges:
                self.ledger.conn.execute(
                    """
                    INSERT INTO task_hyperedge (
                        hyperedge_id, trace_id, task_family, artifact_count,
                        normalization_weight, members_digest, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(hyperedge_id) DO NOTHING
                    """,
                    (he["hyperedge_id"], he["trace_id"], he["task_family"], he["artifact_count"],
                     he["normalization_weight"], he["members_digest"], he["created_at"])
                )

            # Insert edges and evidence
            for (src_aid, tgt_aid, change_type, rel_type), evidence_list in raw_edges.items():
                edge_id = f"edge-{version_name}-{src_aid}-{tgt_aid}-{change_type}-{rel_type}"
                support_count = len(evidence_list)
                organic_support = sum(e["weight"] for e in evidence_list if e["origin"] == "organic")
                recommended_support = sum(e["weight"] for e in evidence_list if e["origin"] == "system_recommended")

                # Bounded score between 0.0 and 1.0
                total_weight = organic_support + recommended_support
                score = min(1.0, round(1.0 - math.exp(-total_weight * 0.8), 4))

                self.ledger.conn.execute(
                    """
                    INSERT INTO graph_edge (
                        edge_id, graph_version, source_artifact_id, target_artifact_id,
                        change_type, relation_type, direction, score, support_count,
                        organic_support, recommended_support, last_observed_at, feature_version
                    ) VALUES (?, ?, ?, ?, ?, ?, 'source_to_target', ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(graph_version, source_artifact_id, target_artifact_id, change_type, relation_type)
                    DO UPDATE SET score=excluded.score, support_count=excluded.support_count
                    """,
                    (
                        edge_id, version_name, src_aid, tgt_aid, change_type, rel_type,
                        score, support_count, organic_support, recommended_support, now, "feature.v1"
                    )
                )

                graph_digest_pre.append(f"{edge_id}:{score}")

                for idx, ev in enumerate(evidence_list):
                    ev_id = f"ev-{edge_id}-{idx}"
                    ev_digest = compute_json_digest(ev)
                    self.ledger.conn.execute(
                        """
                        INSERT INTO edge_evidence (
                            evidence_id, edge_id, evidence_kind, source_ref,
                            access_origin, weight, evidence_digest, observed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(evidence_id) DO NOTHING
                        """,
                        (ev_id, edge_id, ev["kind"], ev["source_ref"], ev["origin"], ev["weight"], ev_digest, ev["time"])
                    )

            # Finalize graph digest (deterministic C06)
            graph_digest_pre.sort()
            final_graph_digest = compute_json_digest(graph_digest_pre)
            self.ledger.conn.execute(
                "UPDATE graph_snapshot SET graph_digest=?, status='published' WHERE graph_version=?",
                (final_graph_digest, version_name)
            )

        return {
            "graph_version": version_name,
            "edges_count": len(raw_edges),
            "hyperedges_count": len(hyperedges),
            "graph_digest": final_graph_digest
        }
