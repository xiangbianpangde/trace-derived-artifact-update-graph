# Q3 Auth Rollout Plan

## Milestones
1. Phase 1: Deploy staging cluster.
2. Phase 2: Canary 5% traffic.
3. Phase 3: General availability.

## Rollback Criteria
- HTTP 500 error rate > 0.5% for 5 minutes.
- P99 latency > 200ms.
