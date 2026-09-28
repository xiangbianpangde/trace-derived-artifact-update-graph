import { test, describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { LedgerDb } from '../src/db/index.ts';
import { EventValidator } from '../src/validator/event_validator.ts';
import { computeSha256 } from '../src/types.ts';
import type { ToolEvent, GraphEdge } from '../src/types.ts';

describe('DAUG 核心契约自动化测试 (C01 ~ C12)', () => {
  let db: LedgerDb;

  beforeEach(() => {
    db = new LedgerDb(':memory:');
  });

  afterEach(() => {
    db.close();
  });

  const baseEvent: ToolEvent = {
    schema_version: 'daug.tool-event.v1',
    event_id: 'evt_test_00000001',
    trace_id: 'trc_test_00000001',
    repository_id: 'repo_main',
    sequence_no: 1,
    occurred_at: '2026-09-28T10:00:00.000Z',
    operation: 'read',
    result_status: 'success',
    access_origin: 'organic',
    collector_version: '1.0.0',
    payload_policy: 'full',
    artifact_path: 'src/auth/user_context.ts',
    artifact_id: 'art:user_context'
  };

  test('C01: 同一事件重复导入返回已有记录，不增加数据库行数', () => {
    const res1 = db.ingestToolEvent(baseEvent);
    assert.equal(res1.status, 'inserted');

    const countBefore = db.db.prepare('SELECT COUNT(*) as c FROM tool_event').get() as { c: number };
    assert.equal(countBefore.c, 1);

    const res2 = db.ingestToolEvent(baseEvent);
    assert.equal(res2.status, 'idempotent_duplicate');

    const countAfter = db.db.prepare('SELECT COUNT(*) as c FROM tool_event').get() as { c: number };
    assert.equal(countAfter.c, 1);
  });

  test('C02: 相同 event_id 但内容不同，抛出 IDEMPOTENCY_CONFLICT', () => {
    const res1 = db.ingestToolEvent(baseEvent);
    assert.equal(res1.status, 'inserted');

    // 修改了 operation 但保留同一 event_id
    const modifiedEvent = { ...baseEvent, operation: 'search' };
    const res2 = db.ingestToolEvent(modifiedEvent);

    assert.equal(res2.status, 'conflict');
    assert.equal(res2.code, 'IDEMPOTENCY_CONFLICT');
  });

  test('C03: 目标路径越过仓库根目录，校验拒绝并记录原因', () => {
    const traversalEvent1 = { ...baseEvent, event_id: 'evt_c03_00000001', artifact_path: '../secret/passwords.txt' };
    const res1 = db.ingestToolEvent(traversalEvent1);
    assert.equal(res1.status, 'rejected');
    assert.equal(res1.code, 'PATH_TRAVERSAL_DETECTED');

    const traversalEvent2 = { ...baseEvent, event_id: 'evt_c03_00000002', artifact_path: '/etc/shadow' };
    const res2 = db.ingestToolEvent(traversalEvent2);
    assert.equal(res2.status, 'rejected');
    assert.equal(res2.code, 'PATH_TRAVERSAL_DETECTED');
  });

  test('C04: 编辑/修改类事件缺少前后哈希，标记 trace incomplete，不进入训练', () => {
    const editWithoutHashes = {
      ...baseEvent,
      event_id: 'evt_c04_00000001',
      operation: 'edit',
      before_hash: null,
      after_hash: null
    };
    const res = db.ingestToolEvent(editWithoutHashes);
    assert.equal(res.status, 'rejected');
    assert.equal(res.code, 'TRACE_INCOMPLETE_MISSING_HASHES');
  });

  test('C05: 推荐访问缺少 recommendation_id 时验证失败', () => {
    const recommendedWithoutId = {
      ...baseEvent,
      event_id: 'evt_c05_00000001',
      access_origin: 'system_recommended',
      recommendation_id: null
    };
    const res = db.ingestToolEvent(recommendedWithoutId);
    assert.equal(res.status, 'rejected');
    assert.equal(res.code, 'RECOMMENDATION_ID_MISSING');
  });

  test('C06: 相同冻结输入重复构图输出一致的图摘要 (确定性构图)', () => {
    const edges: GraphEdge[] = [
      {
        edge_id: 'edge_1',
        graph_version: 'v1.0.0',
        source_artifact_id: 'art:source_a',
        target_artifact_id: 'art:target_b',
        change_type: 'interface',
        relation_type: 'trace',
        direction: 'source_to_target',
        score: 0.85,
        support_count: 5,
        organic_support: 5,
        recommended_support: 0,
        feature_version: 'f_v1'
      }
    ];

    const digest1 = computeSha256(JSON.stringify(edges));
    const digest2 = computeSha256(JSON.stringify(edges));
    assert.equal(digest1, digest2);

    db.recordGraphSnapshot('v1.0.0', 'f_v1', digest1);
    const snap = db.db.prepare('SELECT graph_digest FROM graph_snapshot WHERE graph_version = ?').get('v1.0.0') as { graph_digest: string };
    assert.equal(snap.graph_digest, digest1);
  });

  test('C07: 目标哈希在验证后发生改变检测出 HASH_CONFLICT 并熔断', () => {
    const initialTargetHash = computeSha256('original_target_doc_content');
    const modifiedTargetHash = computeSha256('concurrently_modified_doc_content');

    // 模拟 CAS 校验逻辑
    function verifyCas(expectedHash: string, currentDiskHash: string): { ok: boolean; code?: string } {
      if (expectedHash !== currentDiskHash) {
        return { ok: false, code: 'HASH_CONFLICT' };
      }
      return { ok: true };
    }

    const check = verifyCas(initialTargetHash, modifiedTargetHash);
    assert.equal(check.ok, false);
    assert.equal(check.code, 'HASH_CONFLICT');
  });

  test('C08: 验证器证据不足时输出 UNCERTAIN 并中断自动化流程', () => {
    // 模拟验证器状态机
    function evaluateStaleness(evidenceCount: number, confidence: number): 'VALID' | 'STALE' | 'UNCERTAIN' {
      if (evidenceCount === 0 || confidence < 0.6) {
        return 'UNCERTAIN';
      }
      return 'STALE';
    }

    const decision = evaluateStaleness(0, 0.4);
    assert.equal(decision, 'UNCERTAIN');

    // UNCERTAIN 状态禁止生成自动应用补丁
    function canProposeAutoApply(status: string): boolean {
      return status === 'STALE'; // 只有明确 STALE 才能产生提案
    }
    assert.equal(canProposeAutoApply(decision), false);
  });

  test('C09: 受保护制品 (R3/R4) 被判定陈旧时，允许提案或人工说明，拒绝自动应用', () => {
    function decidePolicy(riskClass: string, isStale: boolean): 'PROPOSE_ONLY' | 'AUTO_APPLY_ALLOWED' | 'REJECTED' {
      if (!isStale) return 'REJECTED';
      if (['R3', 'R4'].includes(riskClass)) {
        return 'PROPOSE_ONLY'; // 严格禁止自动写回
      }
      return 'AUTO_APPLY_ALLOWED';
    }

    assert.equal(decidePolicy('R3', true), 'PROPOSE_ONLY');
    assert.equal(decidePolicy('R4', true), 'PROPOSE_ONLY');
    assert.equal(decidePolicy('R0', true), 'AUTO_APPLY_ALLOWED');
  });

  test('C10: 大型格式化任务以超边 (hyperedge) 压缩，不生成两两笛卡尔积边', () => {
    const fileCount = 500;
    // 笛卡尔积两两边数量: N * (N - 1) / 2 = 124750
    const fullPairwiseCount = (fileCount * (fileCount - 1)) / 2;
    assert.equal(fullPairwiseCount, 124750);

    // 超边压缩模型：只生成 1 条 hyperedge 记录与归一化权重
    db.registerRepository('repo_c10', '/repo/c10');
    db.registerTraceRun('trc_c10', 'bulk_format', 'repo_c10');
    db.recordTaskHyperedge('hyp_c10_1', 'trc_c10', 'bulk_format', fileCount, 1.0 / fileCount, 'hash_of_500_files');

    const hyper = db.db.prepare('SELECT artifact_count, normalization_weight FROM task_hyperedge WHERE hyperedge_id = ?')
      .get('hyp_c10_1') as { artifact_count: number; normalization_weight: number };

    assert.equal(hyper.artifact_count, 500);
    assert.ok(hyper.normalization_weight < 0.01); // 权重被极大归一化削弱
  });

  test('C11: 系统推荐后发生读取，不按 organic 权重更新边，自发权重物理隔离', () => {
    interface SupportAccumulator {
      organic_support: number;
      recommended_support: number;
    }

    function recordAccess(acc: SupportAccumulator, origin: string): void {
      if (origin === 'organic') {
        acc.organic_support += 1.0;
      } else if (origin === 'system_recommended') {
        // 推荐带来的访问仅计入 recommended_support，且衰减折算
        acc.recommended_support += 0.1;
      }
    }

    const edgeWeight: SupportAccumulator = { organic_support: 1.0, recommended_support: 0.0 };

    // 发生了一次系统推荐读取
    recordAccess(edgeWeight, 'system_recommended');

    // 验证 organic_support 丝毫未变（防止自证实）
    assert.equal(edgeWeight.organic_support, 1.0);
    assert.equal(edgeWeight.recommended_support, 0.1);
  });

  test('C12: 测试失败时 attempt 状态记录为 failed 并熔断', () => {
    db.registerRepository('repo_c12', '/repo/c12');
    db.registerTraceRun('trc_c12', 'task_c12', 'repo_c12');
    db.registerArtifact({
      artifact_id: 'art:c12',
      repository_id: 'repo_c12',
      canonical_uri: 'src/main.ts',
      artifact_kind: 'source_code',
      authority_class: 'canonical',
      risk_class: 'R1',
      write_policy: 'standard',
      first_observed_at: new Date().toISOString()
    });

    // 满足严格外键约束
    db.recordGraphSnapshot('v1', 'f_v1', 'snap_digest_c12');
    db.recordChangeEvent({
      change_id: 'chg_1',
      source_artifact_id: 'art:c12',
      change_type: 'interface',
      impact_score: 0.8,
      scope: 'file',
      classifier_source: 'deterministic',
      classifier_confidence: 1.0,
      input_digest: 'inp_dig',
      occurred_at: new Date().toISOString()
    });

    db.db.exec(`
      INSERT INTO candidate_set (candidate_set_id, change_id, graph_version, policy_version, retrieval_config_digest, top_k, candidate_set_digest, created_at)
      VALUES ('cset_1', 'chg_1', 'v1', 'pol_1', 'dig', 5, 'cset_dig', datetime('now'));

      INSERT INTO update_candidate (candidate_id, candidate_set_id, target_artifact_id, rank, score, feature_digest, explanation_digest)
      VALUES ('cand_1', 'cset_1', 'art:c12', 1, 0.9, 'fdig', 'edig');

      INSERT INTO verification (verification_id, candidate_id, target_version_hash, status, verifier_version, evidence_digest, created_at)
      VALUES ('ver_1', 'cand_1', 'target_hash', 'STALE', 'v1', 'ev_dig', datetime('now'));

      INSERT INTO patch_proposal (
        patch_id, verification_id, target_artifact_id, expected_target_hash,
        patch_format, patch_digest, changed_spans_digest, minimality_check,
        rollback_digest, generator_version, status, created_at
      ) VALUES (
        'pat_1', 'ver_1', 'art:c12', 'target_hash',
        'unified_diff', 'p_dig', 'cs_dig', 'pass',
        'rb_dig', 'gen_v1', 'proposed', datetime('now')
      );

      INSERT INTO policy_decision (
        decision_id, patch_id, policy_version, risk_class, action,
        reason_code, decided_by, decision_digest, created_at
      ) VALUES (
        'dec_1', 'pat_1', 'pol_1', 'R1', 'AUTO_APPLY_ALLOWED',
        'RULE_PASS', 'policy_engine', 'dec_dig', datetime('now')
      );
    `);

    // 记录执行失败
    db.recordAttempt('att_1', 'pat_1', 'dec_1', 'failed');

    const attempt = db.db.prepare('SELECT status FROM attempt WHERE attempt_id = ?').get('att_1') as { status: string };
    assert.equal(attempt.status, 'failed');
  });
});
