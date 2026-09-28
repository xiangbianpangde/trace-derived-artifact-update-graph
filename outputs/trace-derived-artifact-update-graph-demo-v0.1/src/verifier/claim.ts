import { computeSha256 } from '../types.ts';
import type { ClaimSpan } from '../types.ts';
import type { DiffSymbolChange } from './verifier.ts';

export interface DetailedClaimSpan extends ClaimSpan {
  section_path: string;
  line_start: number;
  line_end: number;
  counter_evidence: string;
  confidence: number;
  violation_type:
    | 'INCONSISTENT_FIELD_DECLARATION'
    | 'DEPRECATED_SYMBOL_REFERENCE'
    | 'REMOVED_CONFIGURATION_KEY'
    | 'SIGNATURE_MISMATCH';
}

export interface MarkdownSection {
  title: string;
  level: number;
  path: string;
  startLine: number;
  endLine: number;
  content: string;
}

export class MarkdownClaimParser {
  /**
   * 将 Markdown 文档解析为层级 Section 树与行号映射
   */
  public parseSections(markdownContent: string): MarkdownSection[] {
    const lines = markdownContent.split('\n');
    const sections: MarkdownSection[] = [];

    let currentSection: MarkdownSection = {
      title: 'Root',
      level: 0,
      path: 'Root',
      startLine: 1,
      endLine: lines.length,
      content: ''
    };

    const pathStack: { title: string; level: number }[] = [];
    const sectionLines: string[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const headerMatch = line.match(/^(#{1,6})\s+(.*)$/);

      if (headerMatch) {
        if (sectionLines.length > 0) {
          currentSection.endLine = i;
          currentSection.content = sectionLines.join('\n');
          sections.push({ ...currentSection });
          sectionLines.length = 0;
        }

        const level = headerMatch[1].length;
        const title = headerMatch[2].trim();

        // 维护层级栈
        while (pathStack.length > 0 && pathStack[pathStack.length - 1].level >= level) {
          pathStack.pop();
        }
        pathStack.push({ title, level });

        const sectionPath = pathStack.map(p => p.title).join(' > ');
        currentSection = {
          title,
          level,
          path: sectionPath,
          startLine: i + 1,
          endLine: lines.length,
          content: ''
        };
      }
      sectionLines.push(line);
    }

    if (sectionLines.length > 0) {
      currentSection.endLine = lines.length;
      currentSection.content = sectionLines.join('\n');
      sections.push(currentSection);
    }

    return sections;
  }
}

export class FineGrainedClaimVerifier {
  private parser = new MarkdownClaimParser();

  /**
   * 针对目标 Markdown 文档提取段落/Section 级可解释陈述并检验陈旧性
   */
  public verifyMarkdownClaims(
    targetContent: string,
    symbolChanges: DiffSymbolChange[]
  ): DetailedClaimSpan[] {
    const sections = this.parser.parseSections(targetContent);
    const results: DetailedClaimSpan[] = [];
    const lines = targetContent.split('\n');

    let spanCounter = 1;

    for (const sec of sections) {
      for (let lineNum = sec.startLine; lineNum <= sec.endLine; lineNum++) {
        const lineText = lines[lineNum - 1];
        if (!lineText || lineText.trim().length === 0) continue;

        for (const sym of symbolChanges) {
          if (!sym.oldSymbol) continue;

          // 严格词法边界匹配，避免子串误伤（如 user_id 匹配 user_id_type）
          const symRegex = new RegExp(`\\b${sym.oldSymbol}\\b`);
          if (symRegex.test(lineText)) {
            const counterEvidence = sym.newSymbol
              ? `代码已将 \`${sym.oldSymbol}\` 重构为 \`${sym.newSymbol}\`，此文档陈述仍然引用旧符号。`
              : `代码已删除符号 \`${sym.oldSymbol}\`，此文档陈述引用已废弃接口。`;

            // 计算精确置信度
            // 完整单词匹配 + 处于代码/参数格式中 = 0.98，普通自然语言段落 = 0.92
            const isCodeFormatted = lineText.includes(`\`${sym.oldSymbol}\``) || lineText.includes(`"${sym.oldSymbol}"`);
            const confidence = isCodeFormatted ? 0.98 : 0.92;

            results.push({
              span_no: spanCounter++,
              locator: `${sec.path}#L${lineNum}`,
              section_path: sec.path,
              line_start: lineNum,
              line_end: lineNum,
              claim_text: lineText.trim(),
              claim_digest: computeSha256(lineText.trim()),
              reason_code: 'DEPRECATED_SYMBOL_REFERENCE',
              violation_type: sym.newSymbol ? 'INCONSISTENT_FIELD_DECLARATION' : 'DEPRECATED_SYMBOL_REFERENCE',
              counter_evidence: counterEvidence,
              confidence,
              evidence_ids: [`sym_${sym.oldSymbol}_to_${sym.newSymbol || 'deleted'}`]
            });
          }
        }
      }
    }

    return results;
  }
}
