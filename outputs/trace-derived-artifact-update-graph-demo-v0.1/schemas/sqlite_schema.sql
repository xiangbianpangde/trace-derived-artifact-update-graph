PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE schema_meta (
  schema_version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE repository (
  repository_id TEXT PRIMARY KEY,
  canonical_root TEXT NOT NULL,
  root_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (canonical_root)
);

CREATE TABLE trace_run (
  trace_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  repository_id TEXT NOT NULL REFERENCES repository(repository_id),
  started_at TEXT NOT NULL,
  ended_at TEXT,
  origin_mode TEXT NOT NULL CHECK (origin_mode IN ('organic', 'assisted', 'replay')),
  collector_version TEXT NOT NULL,
  completeness TEXT NOT NULL CHECK (completeness IN ('complete', 'partial', 'unknown')),
  trace_digest TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE artifact (
  artifact_id TEXT PRIMARY KEY,
  repository_id TEXT NOT NULL REFERENCES repository(repository_id),
  canonical_uri TEXT NOT NULL,
  artifact_kind TEXT NOT NULL,
  authority_class TEXT NOT NULL CHECK (authority_class IN ('canonical', 'derived', 'working', 'external_snapshot')),
  risk_class TEXT NOT NULL CHECK (risk_class IN ('R0', 'R1', 'R2', 'R3', 'R4')),
  owner_role TEXT,
  write_policy TEXT NOT NULL,
  first_observed_at TEXT NOT NULL,
  retired_at TEXT,
  UNIQUE (repository_id, canonical_uri)
);

CREATE TABLE artifact_alias (
  repository_id TEXT NOT NULL REFERENCES repository(repository_id),
  alias_uri TEXT NOT NULL,
  artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  valid_from TEXT NOT NULL,
  valid_until TEXT,
  evidence_id TEXT,
  PRIMARY KEY (repository_id, alias_uri, valid_from)
);

CREATE TABLE artifact_version (
  artifact_version_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  content_hash TEXT NOT NULL,
  version_ref TEXT,
  size_bytes INTEGER CHECK (size_bytes IS NULL OR size_bytes >= 0),
  observed_at TEXT NOT NULL,
  metadata_digest TEXT,
  UNIQUE (artifact_id, content_hash)
);

CREATE TABLE tool_event (
  event_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL REFERENCES trace_run(trace_id),
  repository_id TEXT NOT NULL REFERENCES repository(repository_id),
  sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
  parent_event_id TEXT REFERENCES tool_event(event_id),
  occurred_at TEXT NOT NULL,
  tool_name TEXT,
  operation TEXT NOT NULL CHECK (operation IN ('read', 'search', 'edit', 'write', 'delete', 'test', 'execute', 'commit', 'approve', 'reject')),
  artifact_id TEXT REFERENCES artifact(artifact_id),
  artifact_path TEXT,
  target_selector TEXT,
  input_digest TEXT,
  output_digest TEXT,
  before_hash TEXT,
  after_hash TEXT,
  diff_digest TEXT,
  result_status TEXT NOT NULL CHECK (result_status IN ('success', 'failure', 'cancelled', 'unknown')),
  exit_code INTEGER,
  access_origin TEXT NOT NULL CHECK (access_origin IN ('organic', 'system_recommended', 'human_directed', 'replay', 'unknown')),
  recommendation_id TEXT,
  collector_version TEXT NOT NULL,
  payload_policy TEXT NOT NULL,
  event_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (trace_id, sequence_no),
  CHECK (access_origin <> 'system_recommended' OR recommendation_id IS NOT NULL)
);

CREATE TABLE change_event (
  change_id TEXT PRIMARY KEY,
  trace_id TEXT REFERENCES trace_run(trace_id),
  source_artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  before_version_id TEXT REFERENCES artifact_version(artifact_version_id),
  after_version_id TEXT REFERENCES artifact_version(artifact_version_id),
  change_type TEXT NOT NULL CHECK (change_type IN ('refactor', 'rename', 'interface', 'schema', 'behavior', 'policy', 'configuration', 'documentation', 'deletion', 'unknown')),
  impact_score REAL NOT NULL CHECK (impact_score >= 0.0 AND impact_score <= 1.0),
  scope TEXT NOT NULL CHECK (scope IN ('symbol', 'file', 'module', 'repository')),
  classifier_source TEXT NOT NULL CHECK (classifier_source IN ('deterministic', 'model', 'human')),
  classifier_confidence REAL NOT NULL CHECK (classifier_confidence >= 0.0 AND classifier_confidence <= 1.0),
  input_digest TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);

CREATE TABLE graph_snapshot (
  graph_version TEXT PRIMARY KEY,
  built_until TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  config_digest TEXT NOT NULL,
  input_digest TEXT NOT NULL,
  graph_digest TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('building', 'published', 'failed')),
  created_at TEXT NOT NULL
);

CREATE TABLE graph_edge (
  edge_id TEXT PRIMARY KEY,
  graph_version TEXT NOT NULL REFERENCES graph_snapshot(graph_version),
  source_artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  target_artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  change_type TEXT NOT NULL,
  relation_type TEXT NOT NULL CHECK (relation_type IN ('trace', 'cochange', 'static', 'reference', 'semantic', 'task_family', 'fused')),
  direction TEXT NOT NULL DEFAULT 'source_to_target' CHECK (direction = 'source_to_target'),
  score REAL NOT NULL CHECK (score >= 0.0 AND score <= 1.0),
  support_count REAL NOT NULL CHECK (support_count >= 0.0),
  organic_support REAL NOT NULL CHECK (organic_support >= 0.0),
  recommended_support REAL NOT NULL CHECK (recommended_support >= 0.0),
  last_observed_at TEXT,
  feature_version TEXT NOT NULL,
  UNIQUE (graph_version, source_artifact_id, target_artifact_id, change_type, relation_type)
);

CREATE TABLE edge_evidence (
  evidence_id TEXT PRIMARY KEY,
  edge_id TEXT NOT NULL REFERENCES graph_edge(edge_id),
  evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('tool_event', 'commit', 'static', 'reference', 'semantic', 'human_label', 'task_hyperedge')),
  source_ref TEXT NOT NULL,
  access_origin TEXT CHECK (access_origin IS NULL OR access_origin IN ('organic', 'system_recommended', 'human_directed', 'replay', 'unknown')),
  weight REAL NOT NULL,
  evidence_digest TEXT NOT NULL,
  observed_at TEXT NOT NULL
);

CREATE TABLE task_hyperedge (
  hyperedge_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL REFERENCES trace_run(trace_id),
  task_family TEXT NOT NULL,
  artifact_count INTEGER NOT NULL CHECK (artifact_count >= 1),
  normalization_weight REAL NOT NULL CHECK (normalization_weight >= 0.0 AND normalization_weight <= 1.0),
  members_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE candidate_set (
  candidate_set_id TEXT PRIMARY KEY,
  change_id TEXT NOT NULL REFERENCES change_event(change_id),
  graph_version TEXT NOT NULL REFERENCES graph_snapshot(graph_version),
  policy_version TEXT NOT NULL,
  retrieval_config_digest TEXT NOT NULL,
  top_k INTEGER NOT NULL CHECK (top_k >= 1),
  candidate_set_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE update_candidate (
  candidate_id TEXT PRIMARY KEY,
  candidate_set_id TEXT NOT NULL REFERENCES candidate_set(candidate_set_id),
  target_artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  rank INTEGER NOT NULL CHECK (rank >= 1),
  score REAL NOT NULL CHECK (score >= 0.0 AND score <= 1.0),
  feature_digest TEXT NOT NULL,
  explanation_digest TEXT NOT NULL,
  trigger_rule TEXT,
  UNIQUE (candidate_set_id, rank),
  UNIQUE (candidate_set_id, target_artifact_id)
);

CREATE TABLE verification (
  verification_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES update_candidate(candidate_id),
  target_version_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('VALID', 'STALE', 'UNCERTAIN', 'NOT_APPLICABLE')),
  confidence REAL CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)),
  verifier_version TEXT NOT NULL,
  evidence_digest TEXT NOT NULL,
  abstention_reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE verification_span (
  verification_id TEXT NOT NULL REFERENCES verification(verification_id),
  span_no INTEGER NOT NULL CHECK (span_no >= 0),
  locator TEXT NOT NULL,
  claim_digest TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  evidence_ids_digest TEXT NOT NULL,
  PRIMARY KEY (verification_id, span_no)
);

CREATE TABLE patch_proposal (
  patch_id TEXT PRIMARY KEY,
  verification_id TEXT NOT NULL UNIQUE REFERENCES verification(verification_id),
  target_artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  expected_target_hash TEXT NOT NULL,
  patch_format TEXT NOT NULL,
  patch_digest TEXT NOT NULL,
  changed_spans_digest TEXT NOT NULL,
  minimality_check TEXT NOT NULL CHECK (minimality_check IN ('pass', 'fail', 'unknown')),
  tests_digest TEXT,
  rollback_digest TEXT NOT NULL,
  generator_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('proposed', 'superseded', 'rejected')),
  created_at TEXT NOT NULL
);

CREATE TABLE policy_decision (
  decision_id TEXT PRIMARY KEY,
  patch_id TEXT NOT NULL REFERENCES patch_proposal(patch_id),
  policy_version TEXT NOT NULL,
  risk_class TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('PROPOSE_ONLY', 'REVIEW_REQUIRED', 'AUTO_APPLY_ALLOWED', 'REJECTED')),
  reason_code TEXT NOT NULL,
  decided_by TEXT NOT NULL,
  decision_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE attempt (
  attempt_id TEXT PRIMARY KEY,
  patch_id TEXT NOT NULL REFERENCES patch_proposal(patch_id),
  decision_id TEXT NOT NULL REFERENCES policy_decision(decision_id),
  previous_attempt_id TEXT REFERENCES attempt(attempt_id),
  status TEXT NOT NULL CHECK (status IN ('created', 'running', 'applied', 'readback_verified', 'tested', 'failed', 'rejected')),
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE application_receipt (
  receipt_id TEXT PRIMARY KEY,
  attempt_id TEXT NOT NULL UNIQUE REFERENCES attempt(attempt_id),
  before_hash TEXT NOT NULL,
  after_hash TEXT,
  workspace_uri TEXT NOT NULL,
  readback_status TEXT NOT NULL CHECK (readback_status IN ('not_run', 'pass', 'fail')),
  test_status TEXT NOT NULL CHECK (test_status IN ('not_run', 'pass', 'fail')),
  rollback_digest TEXT NOT NULL,
  receipt_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE human_label (
  label_id TEXT PRIMARY KEY,
  change_id TEXT NOT NULL REFERENCES change_event(change_id),
  target_artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
  label TEXT NOT NULL CHECK (label IN ('MUST_UPDATE', 'SHOULD_REVIEW', 'NO_UPDATE', 'UNKNOWN')),
  span_locator TEXT,
  annotator_pseudonym TEXT NOT NULL,
  label_guide_version TEXT NOT NULL,
  rationale_digest TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX idx_tool_event_trace_sequence ON tool_event(trace_id, sequence_no);
CREATE INDEX idx_tool_event_artifact_time ON tool_event(artifact_id, occurred_at);
CREATE INDEX idx_artifact_version_artifact_time ON artifact_version(artifact_id, observed_at);
CREATE INDEX idx_edge_lookup ON graph_edge(graph_version, source_artifact_id, change_type, score DESC);
CREATE INDEX idx_edge_evidence_edge ON edge_evidence(edge_id, observed_at);
CREATE INDEX idx_candidate_set_change ON candidate_set(change_id, created_at);
CREATE INDEX idx_candidate_rank ON update_candidate(candidate_set_id, rank);
CREATE INDEX idx_verification_candidate ON verification(candidate_id, created_at);
CREATE INDEX idx_human_label_change_target ON human_label(change_id, target_artifact_id);

INSERT INTO schema_meta(schema_version, applied_at)
VALUES ('daug.sqlite.v1', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

