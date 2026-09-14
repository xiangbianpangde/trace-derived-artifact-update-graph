import fnmatch
from typing import Any, Dict, Optional
from daug.ledger import Ledger, compute_json_digest, current_iso

DEFAULT_RISK_RULES = [
    {"match": "generated/**", "risk_class": "R0", "action": "PROPOSE_ONLY"},
    {"match": "docs/**", "risk_class": "R2", "action": "REVIEW_REQUIRED"},
    {"match": "tests/**", "risk_class": "R2", "action": "REVIEW_REQUIRED"},
    {"match": "config/deployment/**", "risk_class": "R3", "action": "REVIEW_REQUIRED"},
    {"match": "security/**", "risk_class": "R4", "action": "REJECTED"},
    {"match": "policies/**", "risk_class": "R4", "action": "REJECTED"},
    {"match": "**", "risk_class": "R3", "action": "REVIEW_REQUIRED"},
]

class PolicyEngine:
    def __init__(
        self,
        ledger: Ledger,
        mode: str = "propose_only",
        policy_version: str = "daug.policy.v1",
        risk_rules: Optional[list] = None
    ):
        self.ledger = ledger
        self.mode = mode
        self.policy_version = policy_version
        self.risk_rules = risk_rules or DEFAULT_RISK_RULES

    def evaluate_patch(self, patch_id: str, canonical_uri: str) -> Dict[str, Any]:
        # Match risk rule
        matched_rule = None
        for rule in self.risk_rules:
            pattern = rule["match"]
            if fnmatch.fnmatch(canonical_uri, pattern):
                matched_rule = rule
                break

        if not matched_rule:
            matched_rule = {"risk_class": "R3", "action": "REVIEW_REQUIRED"}

        risk_class = matched_rule["risk_class"]
        raw_action = matched_rule["action"]

        # Policy constraints
        if risk_class == "R4":
            action = "REJECTED"
            reason = "PROTECTED_ARTIFACT_HIGH_RISK"
        elif self.mode == "propose_only":
            action = "PROPOSE_ONLY"
            reason = "POLICY_MODE_PROPOSE_ONLY"
        else:
            action = raw_action
            reason = "POLICY_EVALUATED"

        decision_id = f"dec-{patch_id}"
        now = current_iso()
        decision_data = {
            "decision_id": decision_id,
            "patch_id": patch_id,
            "risk_class": risk_class,
            "action": action,
            "reason_code": reason
        }
        decision_digest = compute_json_digest(decision_data)

        with self.ledger.conn:
            self.ledger.conn.execute(
                """
                INSERT INTO policy_decision (
                    decision_id, patch_id, policy_version, risk_class,
                    action, reason_code, decided_by, decision_digest, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    action=excluded.action,
                    reason_code=excluded.reason_code
                """,
                (
                    decision_id, patch_id, self.policy_version, risk_class,
                    action, reason, "policy_engine_v1", decision_digest, now
                )
            )

        return decision_data
