import { computeSha256 } from '../types.ts';
import type { ChangeType, UpdateCandidate, GraphEdge } from '../types.ts';
import { ArtifactUpdateGraph } from './graph.ts';

export interface RankerConfig {
  topK: number;
  weights: {
    trace: number;
    static: number;
    reference: number;
    cochange: number;
    semantic: number;
  };
}

export const DEFAULT_RANKER_CONFIG: RankerConfig = {
  topK: 10,
  weights: {
    trace: 0.35,
    reference: 0.25,
    static: 0.25,
    cochange: 0.10,
    semantic: 0.05
  }
};

export class CandidateRanker {
  private graph: ArtifactUpdateGraph;
  private config: RankerConfig;

  constructor(graph: ArtifactUpdateGraph, config: RankerConfig = DEFAULT_RANKER_CONFIG) {
    this.graph = graph;
    this.config = config;
  }

  /**
   * 计算候选集合
   */
  public rankCandidates(
    candidateSetId: string,
    sourceArtifactId: string,
    changeType: ChangeType
  ): UpdateCandidate[] {
    const edges = this.graph.getEdgesForSource(sourceArtifactId, changeType);

    // 按目标制品聚合多源边
    const targetMap = new Map<string, { totalScore: number; relationScores: Record<string, number> }>();

    for (const edge of edges) {
      const targetId = edge.target_artifact_id;
      if (!targetMap.has(targetId)) {
        targetMap.set(targetId, { totalScore: 0, relationScores: {} });
      }
      const item = targetMap.get(targetId)!;
      item.relationScores[edge.relation_type] = edge.score;

      const w = this.config.weights[edge.relation_type as keyof typeof this.config.weights] || 0.1;
      item.totalScore += edge.score * w;
    }

    // 针对 change_type 进行语义校准
    // 若为局部重构 refactor，对文档施加强抑制（阻尼系数 0.05）
    for (const [targetId, item] of targetMap.entries()) {
      if (changeType === 'refactor') {
        const isDoc = targetId.includes('doc') || targetId.endsWith('.md');
        if (isDoc) {
          item.totalScore *= 0.05; // 大幅衰减
        }
      } else if (changeType === 'interface' || changeType === 'schema') {
        // 接口/契约变化，设计文档通常高度相关，提升得分
        const isDocOrTest = targetId.includes('doc') || targetId.includes('test');
        if (isDocOrTest) {
          item.totalScore = Math.min(1.0, item.totalScore * 1.25);
        }
      }
    }

    // 排序并截取 Top-K
    const sorted = Array.from(targetMap.entries())
      .map(([targetId, info]) => ({
        targetArtifactId: targetId,
        score: Math.min(1.0, Math.max(0.0, info.totalScore)),
        relationScores: info.relationScores
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, this.config.topK);

    return sorted.map((item, index) => {
      const candidateId = `cand_${computeSha256(`${candidateSetId}::${item.targetArtifactId}`).slice(0, 16)}`;
      return {
        candidate_id: candidateId,
        candidate_set_id: candidateSetId,
        target_artifact_id: item.targetArtifactId,
        rank: index + 1,
        score: Number(item.score.toFixed(4)),
        feature_digest: computeSha256(JSON.stringify(item.relationScores)),
        explanation_digest: computeSha256(`rank_${index + 1}_source_${sourceArtifactId}`),
        trigger_rule: `rule_${changeType}_fused`
      };
    });
  }
}
