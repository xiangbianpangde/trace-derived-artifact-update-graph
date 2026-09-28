import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { FineGrainedClaimVerifier, MarkdownClaimParser } from '../src/verifier/claim.ts';
import type { DiffSymbolChange } from '../src/verifier/verifier.ts';

describe('Phase 1 细粒度 Claim Span（陈述级锚点）行级可解释反例证明测试', () => {
  const docMarkdown = `# 身份认证与权限服务设计

## 1. 总体架构
系统采用 JWT 无状态令牌。

## 2. 接口契约
### 2.1 用户上下文协议
系统请求头中携带 \`user_id\` 字段。
在每次 RPC 调用前必须从上下文取出 user_id 进行鉴权。

### 2.2 租户隔离
每个请求根据 tenant_code 路由到特定数据分片。
`;

  test('MarkdownClaimParser 能准确解析层级 Section 树与行号范围', () => {
    const parser = new MarkdownClaimParser();
    const sections = parser.parseSections(docMarkdown);

    assert.ok(sections.length >= 4);

    const userContextSec = sections.find(s => s.title === '2.1 用户上下文协议');
    assert.ok(userContextSec);
    assert.equal(
      userContextSec.path,
      '身份认证与权限服务设计 > 2. 接口契约 > 2.1 用户上下文协议'
    );
    assert.ok(userContextSec.startLine > 0);
    assert.ok(userContextSec.endLine >= userContextSec.startLine);
  });

  test('FineGrainedClaimVerifier 准确输出行级定位 locator、反例证明与高置信度判定', () => {
    const verifier = new FineGrainedClaimVerifier();
    const symbolChanges: DiffSymbolChange[] = [
      {
        oldSymbol: 'user_id',
        newSymbol: 'subject_id',
        isPublic: true,
        type: 'rename'
      }
    ];

    const spans = verifier.verifyMarkdownClaims(docMarkdown, symbolChanges);

    assert.equal(spans.length, 2, 'docMarkdown 中包含两处 user_id 引用，必须全部定位');

    // 验证第一处带有反引号的符号引用
    const span1 = spans[0];
    assert.equal(span1.span_no, 1);
    assert.ok(span1.locator.includes('2.1 用户上下文协议#L'));
    assert.equal(span1.section_path, '身份认证与权限服务设计 > 2. 接口契约 > 2.1 用户上下文协议');
    assert.ok(span1.claim_text.includes('`user_id`'));
    assert.equal(span1.violation_type, 'INCONSISTENT_FIELD_DECLARATION');
    assert.ok(span1.counter_evidence.includes('代码已将 `user_id` 重构为 `subject_id`'));
    assert.equal(span1.confidence, 0.98, '带代码反引号的精确符号匹配置信度应为 0.98');

    // 验证第二处自然语言中的符号引用
    const span2 = spans[1];
    assert.equal(span2.span_no, 2);
    assert.ok(span2.claim_text.includes('user_id 进行鉴权'));
    assert.equal(span2.confidence, 0.92, '自然语言段落匹配置信度应为 0.92');
  });

  test('严格词法边界匹配，不会将局部前缀 (如 user_id_type) 误伤为 user_id 失效', () => {
    const verifier = new FineGrainedClaimVerifier();
    const nonCollidingDoc = `# 字段类型规范\n本接口支持 user_id_type 枚举值。\n`;
    const symbolChanges: DiffSymbolChange[] = [
      {
        oldSymbol: 'user_id',
        newSymbol: 'subject_id',
        isPublic: true,
        type: 'rename'
      }
    ];

    const spans = verifier.verifyMarkdownClaims(nonCollidingDoc, symbolChanges);
    assert.equal(spans.length, 0, '词法边界应当阻止 user_id_type 误伤');
  });
});
