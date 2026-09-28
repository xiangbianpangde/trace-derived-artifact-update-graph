import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { computeSha256 } from '../types.ts';
import type {
  ToolEvent,
  Artifact,
  ArtifactVersion,
  ChangeEvent,
  GraphEdge,
  UpdateCandidate,
  VerificationResult,
  PatchProposal,
  PolicyDecision
} from '../types.ts';
import { EventValidator } from '../validator/event_validator.ts';

export interface IngestResult {
  status: 'inserted' | 'idempotent_duplicate' | 'conflict' | 'rejected';
  event_id?: string;
  code?: string;
  error?: string;
}

export class LedgerDb {
  public db: DatabaseSync;

  constructor(dbPath: string = ':memory:') {
    this.db = new DatabaseSync(dbPath);
    this.init();
  }

  private init() {
    this.db.exec('PRAGMA foreign_keys = ON;');
    this.db.exec('PRAGMA journal_mode = WAL;');

    const schemaPath = join(process.cwd(), 'schemas', 'sqlite_schema.sql');
    let ddl = readFileSync(schemaPath, 'utf8');

    // 过滤掉 PRAGMA 行和可能冲突的语句
    ddl = ddl
      .replace(/^PRAGMA\s+foreign_keys\s*=\s*ON;/gim, '')
      .replace(/^PRAGMA\s+journal_mode\s*=\s*WAL;/gim, '');

    this.db.exec(ddl);
  }

  /**
   * 注册仓库
   */
  public registerRepository(repoId: string, canonicalRoot: string): void {
    const existing = this.db.prepare('SELECT repository_id FROM repository WHERE repository_id = ?').get(repoId);
    if (!existing) {
      const stmt = this.db.prepare(`
        INSERT INTO repository (repository_id, canonical_root, root_digest, created_at)
        VALUES (?, ?, ?, ?)
      `);
      stmt.run(repoId, canonicalRoot, computeSha256(canonicalRoot), new Date().toISOString());
    }
  }

  /**
   * 注册 Trace Run
   */
  public registerTraceRun(traceId: string, taskId: string, repoId: string, originMode: 'organic' | 'assisted' | 'replay' = 'organic'): void {
    const existing = this.db.prepare('SELECT trace_id FROM trace_run WHERE trace_id = ?').get(traceId);
    if (!existing) {
      const stmt = this.db.prepare(`
        INSERT INTO trace_run (trace_id, task_id, repository_id, started_at, origin_mode, collector_version, completeness, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `);
      stmt.run(traceId, taskId, repoId, new Date().toISOString(), originMode, '1.0.0', 'complete', new Date().toISOString());
    }
  }

  /**
   * 注册制品 (Artifact)
   */
  public registerArtifact(artifact: Artifact): void {
    const existing = this.db.prepare('SELECT artifact_id FROM artifact WHERE artifact_id = ?').get(artifact.artifact_id);
    if (!existing) {
      const stmt = this.db.prepare(`
        INSERT INTO artifact (artifact_id, repository_id, canonical_uri, artifact_kind, authority_class, risk_class, write_policy, first_observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `);
      stmt.run(
        artifact.artifact_id,
        artifact.repository_id,
        artifact.canonical_uri,
        artifact.artifact_kind,
        artifact.authority_class,
        artifact.risk_class,
        artifact.write_policy,
        artifact.first_observed_at || new Date().toISOString()
      );
    }
  }

  /**
   * 记录制品版本 (Artifact Version)
   */
  public recordArtifactVersion(version: ArtifactVersion): void {
    const existing = this.db.prepare('SELECT artifact_version_id FROM artifact_version WHERE artifact_id = ? AND content_hash = ?')
      .get(version.artifact_id, version.content_hash);
    if (!existing) {
      const stmt = this.db.prepare(`
        INSERT INTO artifact_version (artifact_version_id, artifact_id, content_hash, version_ref, size_bytes, observed_at)
        VALUES (?, ?, ?, ?, ?, ?)
      `);
      stmt.run(
        version.artifact_version_id,
        version.artifact_id,
        version.content_hash,
        version.version_ref ?? null,
        version.size_bytes ?? null,
        version.observed_at || new Date().toISOString()
      );
    }
  }

  /**
   * 导入单个工具事件，严格执行 C01 (幂等导入) 与 C02 (幂等冲突)
   */
  public ingestToolEvent(rawEvent: unknown): IngestResult {
    const validation = EventValidator.validateEvent(rawEvent);
    if (!validation.ok) {
      return {
        status: 'rejected',
        code: validation.code,
        error: validation.error
      };
    }

    const e = validation.event;

    // 确保外键依赖存在
    this.registerRepository(e.repository_id, `/repo/${e.repository_id}`);
    this.registerTraceRun(e.trace_id, `task-${e.trace_id}`, e.repository_id, e.access_origin === 'system_recommended' ? 'assisted' : 'organic');

    if (e.artifact_id && e.artifact_path) {
      this.registerArtifact({
        artifact_id: e.artifact_id,
        repository_id: e.repository_id,
        canonical_uri: e.artifact_path,
        artifact_kind: e.artifact_path.endsWith('.md') ? 'design_doc' : 'source_code',
        authority_class: 'canonical',
        risk_class: e.artifact_path.includes('policy') ? 'R3' : 'R1',
        write_policy: 'proposal_required',
        first_observed_at: e.occurred_at
      });
    }

    // 检查是否有相同的 event_id 已存在
    const existing = this.db.prepare('SELECT event_id, event_digest FROM tool_event WHERE event_id = ?').get(e.event_id) as
      | { event_id: string; event_digest: string }
      | undefined;

    if (existing) {
      // C01 & C02 判定
      if (existing.event_digest === e.event_digest) {
        // C01: 同一事件重复导入，返回已有记录，不增加行数
        return {
          status: 'idempotent_duplicate',
          event_id: e.event_id
        };
      } else {
        // C02: 相同 event_id 但内容不同，抛出 IDEMPOTENCY_CONFLICT
        return {
          status: 'conflict',
          code: 'IDEMPOTENCY_CONFLICT',
          error: `Event ${e.event_id} already exists with different digest (Contract C02)`
        };
      }
    }

    // 插入事件
    const stmt = this.db.prepare(`
      INSERT INTO tool_event (
        event_id, trace_id, repository_id, sequence_no, parent_event_id,
        occurred_at, tool_name, operation, artifact_id, artifact_path,
        target_selector, input_digest, output_digest, before_hash, after_hash,
        diff_digest, result_status, exit_code, access_origin, recommendation_id,
        collector_version, payload_policy, event_digest, created_at
      ) VALUES (
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?, ?,
        ?, ?, ?, ?
      )
    `);

    stmt.run(
      e.event_id,
      e.trace_id,
      e.repository_id,
      e.sequence_no,
      e.parent_event_id ?? null,
      e.occurred_at,
      e.tool_name ?? null,
      e.operation,
      e.artifact_id ?? null,
      e.artifact_path ?? null,
      e.target_selector ?? null,
      e.input_digest ?? null,
      e.output_digest ?? null,
      e.before_hash ?? null,
      e.after_hash ?? null,
      e.diff_digest ?? null,
      e.result_status,
      e.exit_code ?? null,
      e.access_origin,
      e.recommendation_id ?? null,
      e.collector_version,
      e.payload_policy,
      e.event_digest!,
      e.created_at || new Date().toISOString()
    );

    return {
      status: 'inserted',
      event_id: e.event_id
    };
  }

  /**
   * 记录变更事件 (Change Event)
   */
  public recordChangeEvent(change: ChangeEvent): void {
    const stmt = this.db.prepare(`
      INSERT INTO change_event (
        change_id, trace_id, source_artifact_id, before_version_id, after_version_id,
        change_type, impact_score, scope, classifier_source, classifier_confidence,
        input_digest, occurred_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      change.change_id,
      change.trace_id ?? null,
      change.source_artifact_id,
      change.before_version_id ?? null,
      change.after_version_id ?? null,
      change.change_type,
      change.impact_score,
      change.scope,
      change.classifier_source,
      change.classifier_confidence,
      change.input_digest,
      change.occurred_at
    );
  }

  /**
   * 记录图快照 (Graph Snapshot)
   */
  public recordGraphSnapshot(version: string, featureVersion: string, graphDigest: string): void {
    const existing = this.db.prepare('SELECT graph_version FROM graph_snapshot WHERE graph_version = ?').get(version);
    if (!existing) {
      const stmt = this.db.prepare(`
        INSERT INTO graph_snapshot (graph_version, built_until, feature_version, config_digest, input_digest, graph_digest, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      `);
      stmt.run(
        version,
        new Date().toISOString(),
        featureVersion,
        computeSha256(version),
        computeSha256('default_input'),
        graphDigest,
        'published',
        new Date().toISOString()
      );
    }
  }

  /**
   * 插入图边 (Graph Edge)
   */
  public insertGraphEdge(edge: GraphEdge): void {
    const stmt = this.db.prepare(`
      INSERT INTO graph_edge (
        edge_id, graph_version, source_artifact_id, target_artifact_id,
        change_type, relation_type, direction, score, support_count,
        organic_support, recommended_support, last_observed_at, feature_version
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      edge.edge_id,
      edge.graph_version,
      edge.source_artifact_id,
      edge.target_artifact_id,
      edge.change_type,
      edge.relation_type,
      'source_to_target',
      edge.score,
      edge.support_count,
      edge.organic_support,
      edge.recommended_support,
      edge.last_observed_at ?? null,
      edge.feature_version
    );
  }

  /**
   * 记录超边 (Task Hyperedge)
   */
  public recordTaskHyperedge(hyperedgeId: string, traceId: string, taskFamily: string, artifactCount: number, normWeight: number, membersDigest: string): void {
    const stmt = this.db.prepare(`
      INSERT INTO task_hyperedge (hyperedge_id, trace_id, task_family, artifact_count, normalization_weight, members_digest, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(hyperedgeId, traceId, taskFamily, artifactCount, normWeight, membersDigest, new Date().toISOString());
  }

  /**
   * 记录候选集与候选结果 (Candidate Set & Candidates)
   */
  public recordCandidateSet(candidateSetId: string, changeId: string, graphVersion: string, topK: number, candidates: UpdateCandidate[]): void {
    const stmtSet = this.db.prepare(`
      INSERT INTO candidate_set (candidate_set_id, change_id, graph_version, policy_version, retrieval_config_digest, top_k, candidate_set_digest, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmtSet.run(candidateSetId, changeId, graphVersion, '1.0.0', computeSha256('default'), topK, computeSha256(JSON.stringify(candidates)), new Date().toISOString());

    const stmtCand = this.db.prepare(`
      INSERT INTO update_candidate (candidate_id, candidate_set_id, target_artifact_id, rank, score, feature_digest, explanation_digest, trigger_rule)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);

    for (const c of candidates) {
      stmtCand.run(c.candidate_id, candidateSetId, c.target_artifact_id, c.rank, c.score, c.feature_digest, c.explanation_digest, c.trigger_rule ?? null);
    }
  }

  /**
   * 记录陈旧验证结论 (Verification)
   */
  public recordVerification(result: VerificationResult): void {
    const stmt = this.db.prepare(`
      INSERT INTO verification (
        verification_id, candidate_id, target_version_hash, status,
        confidence, verifier_version, evidence_digest, abstention_reason, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      result.verification_id,
      result.candidate_id,
      result.target_version_hash,
      result.status,
      result.confidence ?? null,
      result.verifier_version,
      result.evidence_digest,
      result.abstention_reason ?? null,
      result.created_at
    );

    if (result.spans && result.spans.length > 0) {
      const stmtSpan = this.db.prepare(`
        INSERT INTO verification_span (verification_id, span_no, locator, claim_digest, reason_code, evidence_ids_digest)
        VALUES (?, ?, ?, ?, ?, ?)
      `);
      for (const span of result.spans) {
        stmtSpan.run(
          result.verification_id,
          span.span_no,
          span.locator,
          span.claim_digest,
          span.reason_code,
          computeSha256(JSON.stringify(span.evidence_ids))
        );
      }
    }
  }

  /**
   * 记录补丁提案 (Patch Proposal)
   */
  public recordPatchProposal(proposal: PatchProposal): void {
    const stmt = this.db.prepare(`
      INSERT INTO patch_proposal (
        patch_id, verification_id, target_artifact_id, expected_target_hash,
        patch_format, patch_digest, changed_spans_digest, minimality_check,
        tests_digest, rollback_digest, generator_version, status, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      proposal.patch_id,
      proposal.verification_id,
      proposal.target_artifact_id,
      proposal.expected_target_hash,
      proposal.patch_format,
      proposal.patch_digest,
      proposal.changed_spans_digest,
      proposal.minimality_check,
      proposal.tests_digest ?? null,
      proposal.rollback_digest,
      proposal.generator_version,
      proposal.status,
      proposal.created_at
    );
  }

  /**
   * 记录策略决策 (Policy Decision)
   */
  public recordPolicyDecision(decision: PolicyDecision): void {
    const stmt = this.db.prepare(`
      INSERT INTO policy_decision (
        decision_id, patch_id, policy_version, risk_class, action,
        reason_code, decided_by, decision_digest, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      decision.decision_id,
      decision.patch_id,
      decision.policy_version,
      decision.risk_class,
      decision.action,
      decision.reason_code,
      decision.decided_by,
      decision.decision_digest,
      decision.created_at
    );
  }

  /**
   * 记录 Attempt 状态（覆盖 C12 等测试失败记录）
   */
  public recordAttempt(attemptId: string, patchId: string, decisionId: string, status: string, previousAttemptId?: string): void {
    const stmt = this.db.prepare(`
      INSERT INTO attempt (attempt_id, patch_id, decision_id, previous_attempt_id, status, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `);
    stmt.run(attemptId, patchId, decisionId, previousAttemptId ?? null, status, new Date().toISOString());
  }

  /**
   * 关闭数据库连接
   */
  public close(): void {
    this.db.close();
  }
}
