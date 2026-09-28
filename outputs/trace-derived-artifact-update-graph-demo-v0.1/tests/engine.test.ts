import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { DaugEngine } from '../src/engine.ts';

describe('DAUG 核心引擎流水线端到端测试 (Pipeline & Contract Verification)', () => {
  test('能够从 JSONL 导入真实事件流，构建图并基于代码 Diff 召回失效文档产出 STALE 判定与 CAS 补丁', () => {
    const engine = new DaugEngine(':memory:');

    // 1. 导入示例轨迹
    const tracePath = join(process.cwd(), 'examples', 'demo_trace.jsonl');
    const importRes = engine.importTraceFile(tracePath);

    assert.equal(importRes.total, 8);
    assert.equal(importRes.inserted, 8);
    assert.equal(importRes.rejected, 0);

    // 2. 准备制品当前内容快照
    const designDocContent = `# 认证系统设计文档

当前系统使用请求头中的 user_id 字段作为用户唯一标识进行鉴权。
校验通过后将 user_id 注入全局上下文。
`;
    const filterCodeContent = `// auth_filter.ts
export function filter(req) { return req.header('auth'); }
`;
    const rolloutContent = `# 灰度发布方案
按地区逐步灰度，监控错误率。
`;

    const contents = new Map<string, string>();
    contents.set('artifact-doc-auth-design', designDocContent);
    contents.set('artifact-src-auth-filter', filterCodeContent);
    contents.set('artifact-doc-rollout-plan', rolloutContent);

    // 3. 构造代码差异（接口变更：user_id -> subject_id）
    const diff = `--- a/src/auth/user_context.ts
+++ b/src/auth/user_context.ts
@@ -10,1 +10,1 @@
- export interface UserContext { user_id: string; }
+ export interface UserContext { subject_id: string; }
`;

    // 4. 运行完整流水线
    const res = engine.runPipeline(
      'trace-demo-interface-001',
      'artifact-src-user-context',
      diff,
      'interface',
      contents
    );

    // 验证候选召回
    assert.ok(res.candidates.length > 0);
    const designCand = res.candidates.find(c => c.target_artifact_id === 'artifact-doc-auth-design');
    assert.ok(designCand, '设计文档必须被更新图成功召回');

    // 验证陈旧性判定
    const designVer = res.verifications.find(v => v.candidate_id === designCand.candidate_id);
    assert.ok(designVer);
    assert.equal(designVer.status, 'STALE', '设计文档因为包含旧字段 user_id 必须被判定为 STALE');
    assert.ok(designVer.spans && designVer.spans.length >= 1, '必须生成具体陈述定位 span');

    // 验证 CAS 补丁提案生成
    assert.equal(res.proposals.length, 1, '必须生成对应的补丁提案');
    const proposal = res.proposals[0];
    assert.equal(proposal.target_artifact_id, 'artifact-doc-auth-design');
    assert.equal(proposal.patch_format, 'unified_diff');
    assert.ok(proposal.patch_content.includes('- 当前系统使用请求头中的 user_id 字段作为用户唯一标识进行鉴权。'));
    assert.ok(proposal.patch_content.includes('+ 当前系统使用请求头中的 subject_id 字段作为用户唯一标识进行鉴权。'));
    assert.equal(proposal.minimality_check, 'pass', '补丁必须通过最小性检验');

    // 验证负对照：局部重构 refactor
    const localRefactorDiff = `--- a/src/auth/auth_filter.ts
+++ b/src/auth/auth_filter.ts
@@ -5,1 +5,1 @@
- let local_temp_count = 0;
+ let local_idx = 0;
`;
    const refactorRes = engine.runPipeline(
      'trace-demo-interface-001',
      'artifact-src-auth-filter',
      localRefactorDiff,
      'refactor',
      contents
    );

    // 负对照验证：设计文档绝不产生 STALE 判定，不得产生补丁提案
    const refactorDesignVer = refactorRes.verifications.find(v => {
      const cand = refactorRes.candidates.find(c => c.candidate_id === v.candidate_id);
      return cand?.target_artifact_id === 'artifact-doc-auth-design';
    });
    if (refactorDesignVer) {
      assert.equal(refactorDesignVer.status, 'VALID');
    }
    assert.equal(refactorRes.proposals.length, 0, '局部重构绝不允许产生任何补丁提案');

    // 验证证据不足时的 UNCERTAIN 状态
    const ambiguousDiff = `--- a/unknown.ts
+++ b/unknown.ts
@@ -1,1 +1,1 @@
- // some unparseable comment
+ // some new comment
`;
    const uncertainVer = engine.verifier.verify('cand_ambiguous', designDocContent, ambiguousDiff, 'unknown');
    assert.equal(uncertainVer.status, 'UNCERTAIN', '证据模糊时必须输出 UNCERTAIN');

    engine.close();
  });
});
