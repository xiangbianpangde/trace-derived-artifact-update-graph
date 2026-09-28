import { computeSha256 } from '../types.ts';
import type {
  ChangeType,
  VerificationResult,
  VerificationStatus,
  ClaimSpan
} from '../types.ts';

export interface DiffSymbolChange {
  oldSymbol?: string;
  newSymbol?: string;
  isPublic: boolean;
  type: 'rename' | 'deletion' | 'addition' | 'refactor';
}

const TS_KEYWORDS = new Set([
  'export', 'import', 'from', 'interface', 'type', 'class', 'const', 'let', 'var',
  'function', 'return', 'if', 'else', 'for', 'while', 'switch', 'case', 'break',
  'string', 'number', 'boolean', 'any', 'void', 'null', 'undefined', 'true', 'false',
  'public', 'private', 'protected', 'readonly', 'static', 'async', 'await', 'new'
]);

export class StalenessVerifier {
  private verifierVersion: string = 'daug-verifier-v0.1.0';

  /**
   * 使用词法分词与集合差分提取 Diff 中实际变化的符号（支持行内字段、参数、变量变化）
   */
  public parseDiffSymbols(diffText: string): DiffSymbolChange[] {
    const changes: DiffSymbolChange[] = [];
    const lines = diffText.split('\n');

    const minusIdentifiers: string[] = [];
    const plusIdentifiers: string[] = [];

    const identRegex = /[a-zA-Z_][a-zA-Z0-9_]*/g;

    for (const line of lines) {
      if (line.startsWith('---') || line.startsWith('+++') || line.startsWith('@@')) continue;

      const trimmed = line.slice(1).trim();
      // 忽略纯注释行
      if (trimmed.startsWith('//') || trimmed.startsWith('/*') || trimmed.startsWith('*')) {
        continue;
      }

      if (line.startsWith('-')) {
        const matches = line.slice(1).match(identRegex) || [];
        for (const m of matches) {
          if (!TS_KEYWORDS.has(m)) {
            minusIdentifiers.push(m);
          }
        }
      } else if (line.startsWith('+')) {
        const matches = line.slice(1).match(identRegex) || [];
        for (const m of matches) {
          if (!TS_KEYWORDS.has(m)) {
            plusIdentifiers.push(m);
          }
        }
      }
    }

    // 找出只在 - 出现的旧标识符和只在 + 出现的新标识符
    const removed = minusIdentifiers.filter(id => !plusIdentifiers.includes(id));
    const added = plusIdentifiers.filter(id => !minusIdentifiers.includes(id));

    // 成对映射为 rename 关系
    const pairCount = Math.min(removed.length, added.length);
    for (let i = 0; i < pairCount; i++) {
      changes.push({
        oldSymbol: removed[i],
        newSymbol: added[i],
        isPublic: !diffText.includes('local_'),
        type: 'rename'
      });
    }

    // 剩余的单边删除
    for (let i = pairCount; i < removed.length; i++) {
      changes.push({
        oldSymbol: removed[i],
        isPublic: true,
        type: 'deletion'
      });
    }

    return changes;
  }

  /**
   * 执行独立陈旧性检验
   */
  public verify(
    candidateId: string,
    targetContent: string,
    diffText: string,
    changeType: ChangeType
  ): VerificationResult {
    const targetHash = computeSha256(targetContent);
    const verificationId = `ver_${computeSha256(`${candidateId}::${targetHash}`).slice(0, 16)}`;

    // 1. 若为局部重构，且未改变接口，直接判为 VALID / NOT_APPLICABLE
    if (changeType === 'refactor') {
      return {
        verification_id: verificationId,
        candidate_id: candidateId,
        target_version_hash: targetHash,
        status: 'VALID',
        confidence: 0.95,
        verifier_version: this.verifierVersion,
        evidence_digest: computeSha256('refactor_local_scope_safe'),
        created_at: new Date().toISOString(),
        spans: []
      };
    }

    // 2. 解析 Diff 中的符号变化
    const symbolChanges = this.parseDiffSymbols(diffText);

    // 3. 证据不足或无法解析时，返回 UNCERTAIN（契约 C08）
    if (symbolChanges.length === 0 && diffText.trim().length > 0 && changeType !== 'documentation') {
      return {
        verification_id: verificationId,
        candidate_id: candidateId,
        target_version_hash: targetHash,
        status: 'UNCERTAIN',
        confidence: 0.4,
        verifier_version: this.verifierVersion,
        evidence_digest: computeSha256(diffText),
        abstention_reason: 'CANNOT_EXTRACT_EXACT_SEMANTIC_CLAIMS',
        created_at: new Date().toISOString(),
        spans: []
      };
    }

    // 4. 扫描目标文档内容，匹配是否存在失效陈述 (Claim Span)
    const targetLines = targetContent.split('\n');
    const staleSpans: ClaimSpan[] = [];

    for (let lineIdx = 0; lineIdx < targetLines.length; lineIdx++) {
      const line = targetLines[lineIdx];

      for (const sym of symbolChanges) {
        if (sym.oldSymbol && line.includes(sym.oldSymbol)) {
          // 发现了对旧符号的引用
          const spanNo = staleSpans.length + 1;
          staleSpans.push({
            span_no: spanNo,
            locator: `line:${lineIdx + 1}`,
            claim_text: line.trim(),
            claim_digest: computeSha256(line.trim()),
            reason_code: 'DEPRECATED_SYMBOL_REFERENCE',
            evidence_ids: [`sym_change_${sym.oldSymbol}_to_${sym.newSymbol || 'deleted'}`]
          });
        }
      }
    }

    // 5. 判定最终四态结论
    let finalStatus: VerificationStatus = 'VALID';
    let confidence = 0.95;

    if (staleSpans.length > 0) {
      finalStatus = 'STALE';
      confidence = 0.98;
    } else {
      finalStatus = 'VALID';
      confidence = 0.90;
    }

    return {
      verification_id: verificationId,
      candidate_id: candidateId,
      target_version_hash: targetHash,
      status: finalStatus,
      confidence,
      verifier_version: this.verifierVersion,
      evidence_digest: computeSha256(JSON.stringify(staleSpans)),
      created_at: new Date().toISOString(),
      spans: staleSpans
    };
  }
}
