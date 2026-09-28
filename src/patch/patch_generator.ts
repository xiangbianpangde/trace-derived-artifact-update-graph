import { computeSha256 } from '../types.ts';
import type { PatchProposal, VerificationResult } from '../types.ts';
import type { DiffSymbolChange } from '../verifier/verifier.ts';

export class PatchGenerator {
  private generatorVersion: string = 'daug-patch-gen-v0.1.0';

  /**
   * 生成最小化 Unified Diff 补丁提案
   */
  public generatePatch(
    verification: VerificationResult,
    targetArtifactId: string,
    targetContent: string,
    symbolChanges: DiffSymbolChange[]
  ): PatchProposal | null {
    if (verification.status !== 'STALE' || !verification.spans || verification.spans.length === 0) {
      return null;
    }

    const lines = targetContent.split('\n');
    const patchedLines = [...lines];
    let changedLineCount = 0;

    for (const span of verification.spans) {
      const match = span.locator.match(/line:(\d+)/);
      if (!match) continue;
      const lineNo = parseInt(match[1], 10) - 1;
      if (lineNo >= 0 && lineNo < patchedLines.length) {
        let line = patchedLines[lineNo];
        for (const sym of symbolChanges) {
          if (sym.oldSymbol && sym.newSymbol && line.includes(sym.oldSymbol)) {
            line = line.replaceAll(sym.oldSymbol, sym.newSymbol);
            patchedLines[lineNo] = line;
            changedLineCount++;
          }
        }
      }
    }

    if (changedLineCount === 0) {
      return null;
    }

    // 生成简明 Unified Diff 格式
    const diffBlocks: string[] = [
      `--- a/${targetArtifactId}`,
      `+++ b/${targetArtifactId}`
    ];

    for (const span of verification.spans) {
      const match = span.locator.match(/line:(\d+)/);
      if (match) {
        const lineNo = parseInt(match[1], 10) - 1;
        diffBlocks.push(`@@ -${lineNo + 1},1 +${lineNo + 1},1 @@`);
        diffBlocks.push(`- ${lines[lineNo]}`);
        diffBlocks.push(`+ ${patchedLines[lineNo]}`);
      }
    }

    const patchContent = diffBlocks.join('\n');
    const patchDigest = computeSha256(patchContent);
    const rollbackDigest = computeSha256(targetContent);

    // 最小性检查：只修改必要行，改动行数与 span 数量一致即为 pass
    const minimalityCheck = changedLineCount <= verification.spans.length ? 'pass' : 'fail';

    const patchId = `pat_${computeSha256(`${verification.verification_id}::${patchDigest}`).slice(0, 16)}`;

    return {
      patch_id: patchId,
      verification_id: verification.verification_id,
      target_artifact_id: targetArtifactId,
      expected_target_hash: verification.target_version_hash,
      patch_format: 'unified_diff',
      patch_content: patchContent,
      patch_digest: patchDigest,
      changed_spans_digest: computeSha256(JSON.stringify(verification.spans)),
      minimality_check: minimalityCheck,
      rollback_digest: rollbackDigest,
      generator_version: this.generatorVersion,
      status: 'proposed',
      created_at: new Date().toISOString()
    };
  }
}
