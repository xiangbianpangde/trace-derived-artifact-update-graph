import { test, describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { DaugEngine } from '../src/engine.ts';
import { ArtifactUpdateGraph } from '../src/graph/graph.ts';
import { CandidateRanker } from '../src/graph/ranker.ts';
import type { ChangeType } from '../src/types.ts';

describe('Phase 0 行为测试与场景验证 (D01 ~ D05)', () => {
  let engine: DaugEngine;

  beforeEach(() => {
    engine = new DaugEngine(':memory:');
    // 导入基线轨迹
    const tracePath = join(process.cwd(), 'examples', 'demo_trace.jsonl');
    engine.importTraceFile(tracePath);
  });

  afterEach(() => {
    engine.close();
  });

  test('D01 (场景 A 接口变化): public 字段 user_id 改为 subject_id，设计文档稳居 Top 10 且被判定为 STALE', () => {
    const contents = new Map<string, string>();
    contents.set(
      'artifact-doc-auth-design',
      '# 认证系统架构\n系统在每次请求时读取 user_id 并做白名单校验。\n'
    );
    contents.set(
      'artifact-src-auth-filter',
      'export function authFilter(req) { return req.user_id; }\n'
    );

    const diff = `--- a/src/auth/user_context.ts
+++ b/src/auth/user_context.ts
@@ -5,1 +5,1 @@
- export interface UserContext { user_id: string; }
+ export interface UserContext { subject_id: string; }
`;

    const res = engine.runPipeline(
      'trace-demo-interface-001',
      'artifact-src-user-context',
      diff,
      'interface',
      contents
    );

    // 检查设计文档进入 Top-10
    const designCand = res.candidates.find(c => c.target_artifact_id === 'artifact-doc-auth-design');
    assert.ok(designCand, '设计文档必须在候选集合中');
    assert.ok(designCand.rank <= 10, `设计文档排名必须在 Top 10 之内，实际为第 ${designCand.rank} 名`);

    // 检查验证结论为 STALE
    const designVer = res.verifications.find(v => v.candidate_id === designCand.candidate_id);
    assert.ok(designVer);
    assert.equal(designVer.status, 'STALE');
    assert.ok(designVer.spans && designVer.spans.length >= 1);
    assert.ok(designVer.spans[0].claim_text.includes('user_id'));

    // 检查成功提出最小 Unified Diff 补丁
    assert.ok(res.proposals.length >= 1);
    const patch = res.proposals.find(p => p.target_artifact_id === 'artifact-doc-auth-design');
    assert.ok(patch);
    assert.equal(patch.minimality_check, 'pass');
  });

  test('D02 (场景 B 负对照): 同一模块仅改局部内部变量，不改变公共契约，设计文档不产生补丁提案', () => {
    const contents = new Map<string, string>();
    contents.set(
      'artifact-doc-auth-design',
      '# 认证系统架构\n系统在每次请求时读取 user_id 并做白名单校验。\n'
    );

    const localRefactorDiff = `--- a/src/auth/auth_filter.ts
+++ b/src/auth/auth_filter.ts
@@ -12,1 +12,1 @@
- let local_retry_count = 0;
+ let local_retries = 0;
`;

    const res = engine.runPipeline(
      'trace-demo-interface-001',
      'artifact-src-auth-filter',
      localRefactorDiff,
      'refactor',
      contents
    );

    // 负对照验证：设计文档要么得分为 0 / 极低，要么判定为 VALID，绝对不产生补丁提案
    const designVer = res.verifications.find(v => {
      const cand = res.candidates.find(c => c.candidate_id === v.candidate_id);
      return cand?.target_artifact_id === 'artifact-doc-auth-design';
    });

    if (designVer) {
      assert.equal(designVer.status, 'VALID');
    }
    assert.equal(res.proposals.length, 0, '负对照绝对不允许产出任何补丁提案');
  });

  test('D03 (配置键删除/变更): 删除公开配置项，配置关联制品进入候选集合', () => {
    const graph = new ArtifactUpdateGraph(engine.db, 'v1.0.0');
    // 注入配置制品
    engine.db.registerArtifact({
      artifact_id: 'artifact-cfg-auth-policy',
      repository_id: 'demo-auth-repo',
      canonical_uri: 'config/auth_policy.yaml',
      artifact_kind: 'configuration',
      authority_class: 'canonical',
      risk_class: 'R2',
      write_policy: 'proposal_required',
      first_observed_at: new Date().toISOString()
    });
    engine.db.registerArtifact({
      artifact_id: 'artifact-doc-config-reference',
      repository_id: 'demo-auth-repo',
      canonical_uri: 'docs/config_reference.md',
      artifact_kind: 'design_doc',
      authority_class: 'derived',
      risk_class: 'R1',
      write_policy: 'proposal_required',
      first_observed_at: new Date().toISOString()
    });

    // 建立引用与历史配置协同边
    graph.injectStaticAndReferenceEvidence(
      'artifact-cfg-auth-policy',
      'artifact-doc-config-reference',
      'configuration',
      0.9,
      true
    );

    const ranker = new CandidateRanker(graph);
    const candidates = ranker.rankCandidates('cset_d03', 'artifact-cfg-auth-policy', 'configuration');

    assert.ok(candidates.length > 0);
    const topCand = candidates[0];
    assert.equal(topCand.target_artifact_id, 'artifact-doc-config-reference');
    assert.equal(topCand.rank, 1);
    assert.ok(topCand.score > 0.2, `候选得分应显著高于零，实际为 ${topCand.score}`);
  });

  test('D04 (场景 D 自强化隔离): 系统推荐后读取该文档，得分增量严格衰减受控 (增幅 < 0.05)', () => {
    const graph = new ArtifactUpdateGraph(engine.db, 'v1.0.0');
    const sourceId = 'art:src_test_a';
    const targetId = 'art:doc_test_b';
    const changeType: ChangeType = 'interface';

    // 初始状态：无边
    const initialEdges = graph.getEdgesForSource(sourceId, changeType);
    assert.equal(initialEdges.length, 0);

    // 场景模拟：系统推荐了 targetId，随后 Agent 发生一次读取访问 (system_recommended)
    graph.addEvidence(sourceId, targetId, changeType, {
      sourceArtifactId: sourceId,
      targetArtifactId: targetId,
      relationType: 'trace',
      weight: 1.0,
      origin: 'system_recommended'
    });

    const edgesAfterRec = graph.getEdgesForSource(sourceId, changeType);
    assert.equal(edgesAfterRec.length, 1);
    const edge = edgesAfterRec[0];

    // 自发支持度严格为 0
    assert.equal(edge.organic_support, 0);
    assert.equal(edge.recommended_support, 1.0);
    // 边得分增量受自强化阻尼控制，得分极低 (< 0.05)
    assert.ok(edge.score < 0.05, `单次推荐访问后的边得分必须 < 0.05，实际为 ${edge.score}`);
  });

  test('D05 (场景 C 大任务超边压缩): 500 文件格式化任务，采用超边归一化记录，不产生 124750 条无差别边', () => {
    const traceId = 'trc_bulk_format_500';
    const fileCount = 500;
    const pairwiseFullEdges = (fileCount * (fileCount - 1)) / 2; // 124750

    engine.db.registerTraceRun(traceId, 'task_format', 'demo-auth-repo');
    engine.db.recordTaskHyperedge(
      'hyp_demo_500',
      traceId,
      'bulk_code_formatting',
      fileCount,
      1.0 / fileCount,
      'digest_of_500_format_artifacts'
    );

    // 校验超边写入成功且无笛卡尔积爆发
    const row = engine.db.db.prepare('SELECT artifact_count, normalization_weight FROM task_hyperedge WHERE hyperedge_id = ?')
      .get('hyp_demo_500') as { artifact_count: number; normalization_weight: number };

    assert.equal(row.artifact_count, 500);
    assert.equal(row.normalization_weight, 0.002);

    // 确认数据库中的 graph_edge 表记录数绝对远小于 124750（完全受控）
    const edgeCount = engine.db.db.prepare('SELECT COUNT(*) as c FROM graph_edge').get() as { c: number };
    assert.ok(edgeCount.c < 100);
  });
});
