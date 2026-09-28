import { computeSha256 } from '../types.ts';
import type { ChangeType, GraphEdge } from '../types.ts';
import { LedgerDb } from '../db/index.ts';

export interface RelationEvidence {
  sourceArtifactId: string;
  targetArtifactId: string;
  relationType: 'trace' | 'cochange' | 'static' | 'reference' | 'semantic';
  weight: number;
  origin: 'organic' | 'system_recommended';
}

export class ArtifactUpdateGraph {
  private db: LedgerDb;
  private graphVersion: string;
  private edges: Map<string, GraphEdge> = new Map();

  constructor(db: LedgerDb, graphVersion: string = 'v1.0.0') {
    this.db = db;
    this.graphVersion = graphVersion;
  }

  private edgeKey(sourceId: string, targetId: string, changeType: ChangeType, relationType: string): string {
    return `${sourceId}::${targetId}::${changeType}::${relationType}`;
  }

  /**
   * 添加或更新一条证据边
   */
  public addEvidence(
    sourceId: string,
    targetId: string,
    changeType: ChangeType,
    evidence: RelationEvidence
  ): void {
    if (sourceId === targetId) return; // 忽略自环

    const key = this.edgeKey(sourceId, targetId, changeType, evidence.relationType);
    const existing = this.edges.get(key);

    const isOrganic = evidence.origin === 'organic';
    // 自强化防御：推荐后访问赋予极低折扣权重（0.05），避免推荐自证实
    const effectiveWeight = isOrganic ? evidence.weight : evidence.weight * 0.05;

    if (existing) {
      existing.support_count += 1;
      if (isOrganic) {
        existing.organic_support += evidence.weight;
      } else {
        existing.recommended_support += evidence.weight;
      }
      // 动态更新得分（饱和函数 1 - exp(-k * w)）
      const totalScore = 1 - Math.exp(-(existing.organic_support * 0.5 + existing.recommended_support * 0.05));
      existing.score = Math.min(1.0, Math.max(0.0, totalScore));
    } else {
      const organic = isOrganic ? evidence.weight : 0;
      const recommended = isOrganic ? 0 : evidence.weight;
      const initialScore = isOrganic ? Math.min(1.0, evidence.weight * 0.5) : Math.min(1.0, evidence.weight * 0.025);

      const edge: GraphEdge = {
        edge_id: `edge_${computeSha256(key).slice(0, 16)}`,
        graph_version: this.graphVersion,
        source_artifact_id: sourceId,
        target_artifact_id: targetId,
        change_type: changeType,
        relation_type: evidence.relationType,
        direction: 'source_to_target',
        score: initialScore,
        support_count: 1,
        organic_support: organic,
        recommended_support: recommended,
        feature_version: 'feat_v1'
      };
      this.edges.set(key, edge);
    }
  }

  /**
   * 从数据库已导入的 tool_event 流构建轨迹图
   */
  public buildFromDatabase(traceId: string, changeType: ChangeType): void {
    // 按时间顺序查出本 trace 下的所有事件
    const rows = this.db.db.prepare(`
      SELECT event_id, sequence_no, operation, artifact_id, access_origin
      FROM tool_event
      WHERE trace_id = ? AND artifact_id IS NOT NULL
      ORDER BY sequence_no ASC
    `).all(traceId) as Array<{
      event_id: string;
      sequence_no: number;
      operation: string;
      artifact_id: string;
      access_origin: 'organic' | 'system_recommended';
    }>;

    // 滑动窗口提取轨迹时序关系 (read -> edit, edit -> read/test, test -> edit/read)
    for (let i = 0; i < rows.length; i++) {
      for (let j = i + 1; j < Math.min(rows.length, i + 5); j++) {
        const src = rows[i];
        const tgt = rows[j];
        if (src.artifact_id !== tgt.artifact_id) {
          // 距离越近权重越高
          const dist = j - i;
          const decay = 1.0 / dist;
          this.addEvidence(src.artifact_id, tgt.artifact_id, changeType, {
            sourceArtifactId: src.artifact_id,
            targetArtifactId: tgt.artifact_id,
            relationType: 'trace',
            weight: decay,
            origin: tgt.access_origin
          });
        }
      }
    }
  }

  /**
   * 注入先验静态依赖与显式引用证据
   */
  public injectStaticAndReferenceEvidence(
    sourceId: string,
    targetId: string,
    changeType: ChangeType,
    staticWeight: number = 0.8,
    isExplicitRef: boolean = false
  ): void {
    if (isExplicitRef) {
      this.addEvidence(sourceId, targetId, changeType, {
        sourceArtifactId: sourceId,
        targetArtifactId: targetId,
        relationType: 'reference',
        weight: 1.0,
        origin: 'organic'
      });
    }
    if (staticWeight > 0) {
      this.addEvidence(sourceId, targetId, changeType, {
        sourceArtifactId: sourceId,
        targetArtifactId: targetId,
        relationType: 'static',
        weight: staticWeight,
        origin: 'organic'
      });
    }
  }

  /**
   * 获取针对特定源制品和变更类型的所有关联目标边
   */
  public getEdgesForSource(sourceId: string, changeType: ChangeType): GraphEdge[] {
    const list: GraphEdge[] = [];
    for (const edge of this.edges.values()) {
      if (edge.source_artifact_id === sourceId && edge.change_type === changeType) {
        list.push(edge);
      }
    }
    return list;
  }

  /**
   * 获取所有边并持久化到 SQLite 数据库
   */
  public persistToDb(): void {
    const digest = computeSha256(JSON.stringify(Array.from(this.edges.values())));
    this.db.recordGraphSnapshot(this.graphVersion, 'feat_v1', digest);

    for (const edge of this.edges.values()) {
      this.db.insertGraphEdge(edge);
    }
  }

  public getAllEdges(): GraphEdge[] {
    return Array.from(this.edges.values());
  }
}
