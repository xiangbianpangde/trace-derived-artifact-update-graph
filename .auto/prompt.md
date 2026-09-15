# Autoresearch: DAUG Multi-Modal Candidate Retrieval & Ranking Optimization

## Objective
Optimize DAUG's multi-modal candidate retrieval ranking and cross-modal artifact recall on real-world Agent development traces (GAP dataset) and synthetic contract changes. In long-horizon agentic coding, code evolution leaves design documents, specifications, and data schemas stale. Traditional AST dependency graphs achieve 0% recall on non-imported markdown and schemas. DAUG fuses behavior signals from tool execution traces with static references. This autoresearch session optimizes candidate scoring, reciprocal rank (MRR), and recall while maintaining zero false positives on negative controls and sub-100ms latency.

## Metrics
- **Primary**: `mrr` (unitless ratio [0.0 - 1.0], higher is better) — Mean Reciprocal Rank of target documentation and contract artifacts.
- **Secondary**:
  - `recall_at_5`: Percentage of relevant target items present in top 5.
  - `precision_at_3`: Fraction of top 3 candidates that are relevant target items.
  - `verifier_f1`: Verifier safety score (1.0 = negative controls strictly blocked with zero false staleness, positive stale detected).
  - `latency_ms`: Total retrieval & verification latency in milliseconds.

## How to Run
`./.auto/measure.sh` — outputs `METRIC name=value` lines.
`./.auto/checks.sh` — runs all 21 unit tests.

## Files in Scope
- `daug/retriever.py` — CandidateRetriever: fusion formulas, probabilistic union, relation weights, change-type conditional boosts.
- `daug/graph.py` — GraphBuilder: edge weight aggregation, task hyperedges, organic vs recommended support scaling.
- `daug/verifier.py` — StalenessVerifier: token extraction, confidence thresholds, span locators.

## Off Limits
- `tests/` — Test cases define invariant ground truth and must not be relaxed.
- `02_架构与合同/` — Core architecture specifications and DDL schemas.
- `fixtures/` — Raw trace datasets and demo repositories.

## Constraints
- All 21 unit tests must pass (`./.auto/checks.sh`).
- Negative control must produce 0 false updates (`verifier_f1 == 1.0`).
- Strict CAS hash verification must remain intact.
- Zero third-party dependencies: pure Python 3 standard library only.

## What's Been Tried
### Baseline (Run 0)
- Current implementation: unweighted probabilistic complement fusion `1 - prod(1 - s_i)`.
- Baseline primary metric: `mrr = 0.4815`.
- Secondary metrics: `recall_at_5 = 0.4444`, `precision_at_3 = 0.2222`, `verifier_f1 = 1.0000`, `latency_ms = 22.6`.
- Bottleneck: Scenario 3 (`src/checkpoint.ts`) gets crowded out by test files in top 5; target documentation (`plan/STATUS.md`, `worklog/...`) sits at rank 9-10.
