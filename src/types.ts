import { createHash } from 'node:crypto';

export type OperationType =
  | 'read'
  | 'search'
  | 'edit'
  | 'write'
  | 'delete'
  | 'test'
  | 'execute'
  | 'commit'
  | 'approve'
  | 'reject';

export type AccessOrigin =
  | 'organic'
  | 'system_recommended'
  | 'human_directed'
  | 'replay'
  | 'unknown';

export type ResultStatus = 'success' | 'failure' | 'cancelled' | 'unknown';

export type ChangeType =
  | 'refactor'
  | 'rename'
  | 'interface'
  | 'schema'
  | 'behavior'
  | 'policy'
  | 'configuration'
  | 'documentation'
  | 'deletion'
  | 'unknown';

export type VerificationStatus = 'VALID' | 'STALE' | 'UNCERTAIN' | 'NOT_APPLICABLE';

export type RiskClass = 'R0' | 'R1' | 'R2' | 'R3' | 'R4';

export type PolicyAction =
  | 'PROPOSE_ONLY'
  | 'REVIEW_REQUIRED'
  | 'AUTO_APPLY_ALLOWED'
  | 'REJECTED';

export interface ToolEvent {
  schema_version: 'daug.tool-event.v1';
  event_id: string;
  trace_id: string;
  repository_id: string;
  sequence_no: number;
  occurred_at: string;
  operation: OperationType;
  result_status: ResultStatus;
  access_origin: AccessOrigin;
  collector_version: string;
  payload_policy: string;
  parent_event_id?: string | null;
  tool_name?: string | null;
  artifact_id?: string | null;
  artifact_path?: string | null;
  target_selector?: string | null;
  input_digest?: string | null;
  output_digest?: string | null;
  before_hash?: string | null;
  after_hash?: string | null;
  diff_digest?: string | null;
  exit_code?: number | null;
  recommendation_id?: string | null;
  event_digest?: string;
  created_at?: string;
}

export interface Artifact {
  artifact_id: string;
  repository_id: string;
  canonical_uri: string;
  artifact_kind: string;
  authority_class: 'canonical' | 'derived' | 'working' | 'external_snapshot';
  risk_class: RiskClass;
  write_policy: string;
  owner_role?: string | null;
  first_observed_at: string;
  retired_at?: string | null;
}

export interface ArtifactVersion {
  artifact_version_id: string;
  artifact_id: string;
  content_hash: string;
  version_ref?: string | null;
  size_bytes?: number | null;
  observed_at: string;
  metadata_digest?: string | null;
}

export interface ChangeEvent {
  change_id: string;
  trace_id?: string | null;
  source_artifact_id: string;
  before_version_id?: string | null;
  after_version_id?: string | null;
  change_type: ChangeType;
  impact_score: number;
  scope: 'symbol' | 'file' | 'module' | 'repository';
  classifier_source: 'deterministic' | 'model' | 'human';
  classifier_confidence: number;
  input_digest: string;
  occurred_at: string;
  diff_text?: string;
}

export interface GraphEdge {
  edge_id: string;
  graph_version: string;
  source_artifact_id: string;
  target_artifact_id: string;
  change_type: ChangeType;
  relation_type: 'trace' | 'cochange' | 'static' | 'reference' | 'semantic' | 'task_family' | 'fused';
  direction: 'source_to_target';
  score: number;
  support_count: number;
  organic_support: number;
  recommended_support: number;
  last_observed_at?: string | null;
  feature_version: string;
}

export interface UpdateCandidate {
  candidate_id: string;
  candidate_set_id: string;
  target_artifact_id: string;
  rank: number;
  score: number;
  feature_digest: string;
  explanation_digest: string;
  trigger_rule?: string | null;
}

export interface ClaimSpan {
  span_no: number;
  locator: string;
  claim_text: string;
  claim_digest: string;
  reason_code: string;
  evidence_ids: string[];
}

export interface VerificationResult {
  verification_id: string;
  candidate_id: string;
  target_version_hash: string;
  status: VerificationStatus;
  confidence?: number | null;
  verifier_version: string;
  evidence_digest: string;
  abstention_reason?: string | null;
  created_at: string;
  spans?: ClaimSpan[];
}

export interface PatchProposal {
  patch_id: string;
  verification_id: string;
  target_artifact_id: string;
  expected_target_hash: string;
  patch_format: 'unified_diff' | 'json_patch';
  patch_content: string;
  patch_digest: string;
  changed_spans_digest: string;
  minimality_check: 'pass' | 'fail' | 'unknown';
  tests_digest?: string | null;
  rollback_digest: string;
  generator_version: string;
  status: 'proposed' | 'superseded' | 'rejected';
  created_at: string;
}

export interface PolicyDecision {
  decision_id: string;
  patch_id: string;
  policy_version: string;
  risk_class: RiskClass;
  action: PolicyAction;
  reason_code: string;
  decided_by: string;
  decision_digest: string;
  created_at: string;
}

export function computeSha256(data: string | Buffer): string {
  return createHash('sha256').update(data).digest('hex');
}
