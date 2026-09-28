import type { BenchmarkCase, BenchmarkArtifact } from './dataset_generator.ts';
import type { ChangeType } from '../types.ts';

export interface ModelRankScore {
  targetArtifactId: string;
  score: number;
}

export interface BaselineRunner {
  name: string;
  rank(bCase: BenchmarkCase): ModelRankScore[];
}

/**
 * 基线 1: 时序共变更基线 (Temporal Co-change Baseline)
 * 仅根据训练集中的事件共同出现频率打分
 */
export class CochangeBaseline implements BaselineRunner {
  public name = 'Temporal_Cochange';

  public rank(bCase: BenchmarkCase): ModelRankScore[] {
    const srcId = bCase.testChange.sourceArtifactId;
    const cooccurrences = new Map<string, number>();

    // 统计在同一 trace 中与 srcId 一同出现的制品频次
    for (const evt of bCase.trainEvents) {
      if (evt.artifact_id && evt.artifact_id !== srcId) {
        cooccurrences.set(evt.artifact_id, (cooccurrences.get(evt.artifact_id) || 0) + 1);
      }
    }

    return bCase.artifacts
      .filter(a => a.artifactId !== srcId)
      .map(a => ({
        targetArtifactId: a.artifactId,
        score: cooccurrences.get(a.artifactId) || 0
      }))
      .sort((a, b) => b.score - a.score);
  }
}

/**
 * 基线 2: 静态图扩展基线 (Expanded Static Call Graph Baseline)
 * 仅依赖代码静态 import 和同目录/路径前缀匹配
 */
export class StaticBaseline implements BaselineRunner {
  public name = 'Static_Graph';

  public rank(bCase: BenchmarkCase): ModelRankScore[] {
    const srcId = bCase.testChange.sourceArtifactId;
    const srcArtifact = bCase.artifacts.find(a => a.artifactId === srcId);
    const srcPath = srcArtifact?.path || '';
    const srcDir = srcPath.includes('/') ? srcPath.slice(0, srcPath.lastIndexOf('/')) : '';

    return bCase.artifacts
      .filter(a => a.artifactId !== srcId)
      .map(a => {
        let score = 0;
        // 同一模块/目录加权
        if (srcDir && a.path.startsWith(srcDir)) {
          score += 0.5;
        }
        // 如果内容中显式包含了对方的文件名或路径
        const baseName = srcPath.split('/').pop()?.replace(/\.[^.]+$/, '') || '';
        if (baseName && a.content.includes(baseName)) {
          score += 0.8;
        }
        return { targetArtifactId: a.artifactId, score };
      })
      .sort((a, b) => b.score - a.score);
  }
}

/**
 * 基线 3: 语义检索基线 (Semantic Dense / Bag-of-Words Jaccard Baseline)
 * 仅计算 Diff 与目标制品内容的文本 Token Jaccard 相似度
 */
export class SemanticBaseline implements BaselineRunner {
  public name = 'Semantic_Retrieval';

  public rank(bCase: BenchmarkCase): ModelRankScore[] {
    const srcId = bCase.testChange.sourceArtifactId;
    const diffTokens = new Set(
      bCase.testChange.diffText
        .toLowerCase()
        .replace(/[^a-z0-9_]/g, ' ')
        .split(/\s+/)
        .filter(t => t.length > 2)
    );

    return bCase.artifacts
      .filter(a => a.artifactId !== srcId)
      .map(a => {
        const targetTokens = new Set(
          a.content
            .toLowerCase()
            .replace(/[^a-z0-9_]/g, ' ')
            .split(/\s+/)
            .filter(t => t.length > 2)
        );

        let intersection = 0;
        for (const t of diffTokens) {
          if (targetTokens.has(t)) intersection++;
        }
        const union = diffTokens.size + targetTokens.size - intersection;
        const jaccard = union > 0 ? intersection / union : 0;

        return { targetArtifactId: a.artifactId, score: jaccard };
      })
      .sort((a, b) => b.score - a.score);
  }
}

/**
 * 完整模型: DAUG 动态制品更新图 (融合轨迹 + 静态 + 语义 + 变更类型条件化)
 */
export class DaugModelRunner implements BaselineRunner {
  public name = 'DAUG_Full_Model';

  public rank(bCase: BenchmarkCase): ModelRankScore[] {
    const srcId = bCase.testChange.sourceArtifactId;
    const changeType = bCase.testChange.changeType;

    // 1. 轨迹权重 (严格基于时间切分点 t <= split 的历史轨迹)
    const traceSupport = new Map<string, number>();
    for (const evt of bCase.trainEvents) {
      if (evt.artifact_id && evt.artifact_id !== srcId) {
        traceSupport.set(evt.artifact_id, (traceSupport.get(evt.artifact_id) || 0) + 1.0);
      }
    }

    // 2. 静态与语义基线
    const staticRunner = new StaticBaseline();
    const staticScores = new Map(staticRunner.rank(bCase).map(s => [s.targetArtifactId, s.score]));

    const semanticRunner = new SemanticBaseline();
    const semanticScores = new Map(semanticRunner.rank(bCase).map(s => [s.targetArtifactId, s.score]));

    // 3. 多源融合与 ChangeType 调节
    return bCase.artifacts
      .filter(a => a.artifactId !== srcId)
      .map(a => {
        const sTrace = Math.min(1.0, (traceSupport.get(a.artifactId) || 0) * 0.5);
        const sStatic = staticScores.get(a.artifactId) || 0;
        const sSemantic = semanticScores.get(a.artifactId) || 0;

        let total = 0.40 * sTrace + 0.30 * sStatic + 0.30 * sSemantic;

        // 变更类型条件化：接口/模式改变时，大幅拉升设计文档的复核概率
        if ((changeType === 'interface' || changeType === 'schema') && a.kind === 'design_doc') {
          total = Math.min(1.0, total * 1.5 + 0.2);
        }

        return {
          targetArtifactId: a.artifactId,
          score: Number(total.toFixed(4))
        };
      })
      .sort((a, b) => b.score - a.score);
  }
}
