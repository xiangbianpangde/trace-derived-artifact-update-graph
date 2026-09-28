import { LedgerDb } from './db/index.ts';
import { TraceImporter } from './trace/importer.ts';
import { CasRegistry } from './cas/cas.ts';
import { ArtifactUpdateGraph } from './graph/graph.ts';
import { CandidateRanker } from './graph/ranker.ts';
import { StalenessVerifier } from './verifier/verifier.ts';
import { PatchGenerator } from './patch/patch_generator.ts';
import type {
  ChangeType,
  UpdateCandidate,
  VerificationResult,
  PatchProposal
} from './types.ts';

export interface PipelineExecutionResult {
  traceId: string;
  changeId: string;
  candidates: UpdateCandidate[];
  verifications: VerificationResult[];
  proposals: PatchProposal[];
}

export class DaugEngine {
  public db: LedgerDb;
  public cas: CasRegistry;
  public importer: TraceImporter;
  public verifier: StalenessVerifier;
  public patchGen: PatchGenerator;

  constructor(dbPath: string = ':memory:') {
    this.db = new LedgerDb(dbPath);
    this.cas = new CasRegistry();
    this.importer = new TraceImporter(this.db);
    this.verifier = new StalenessVerifier();
    this.patchGen = new PatchGenerator();
  }

  /**
   * 从 JSONL 文件导入事件流
   */
  public importTraceFile(filePath: string) {
    return this.importer.importJsonlFile(filePath);
  }

  /**
   * 注册工作区制品内容快照至 CAS
   */
  public registerArtifactSnapshot(artifactId: string, content: string) {
    return this.cas.registerContent(artifactId, content);
  }

  /**
   * 执行完整的分析与验证流水线
   */
  public runPipeline(
    traceId: string,
    sourceArtifactId: string,
    diffText: string,
    changeType: ChangeType,
    targetArtifactContents: Map<string, string>
  ): PipelineExecutionResult {
    // 1. 构建加权更新图
    const graph = new ArtifactUpdateGraph(this.db, 'v1.0.0');
    graph.buildFromDatabase(traceId, changeType);

    // 2. 候选排序
    const ranker = new CandidateRanker(graph);
    const candidateSetId = `cset_${Date.now()}`;
    const candidates = ranker.rankCandidates(candidateSetId, sourceArtifactId, changeType);

    // 3. 记录候选集至 DB
    const changeId = `chg_${Date.now()}`;
    this.db.recordGraphSnapshot('v1.0.0', 'feat_v1', 'graph_digest_placeholder');
    this.db.recordChangeEvent({
      change_id: changeId,
      trace_id: traceId,
      source_artifact_id: sourceArtifactId,
      change_type: changeType,
      impact_score: 0.8,
      scope: 'file',
      classifier_source: 'deterministic',
      classifier_confidence: 1.0,
      input_digest: 'diff_digest',
      occurred_at: new Date().toISOString()
    });

    this.db.recordCandidateSet(candidateSetId, changeId, 'v1.0.0', 10, candidates);

    const verifications: VerificationResult[] = [];
    const proposals: PatchProposal[] = [];

    const symbols = this.verifier.parseDiffSymbols(diffText);

    // 4. 对每个候选制品执行陈旧性验证
    for (const cand of candidates) {
      const content = targetArtifactContents.get(cand.target_artifact_id) || '';
      const verRes = this.verifier.verify(cand.candidate_id, content, diffText, changeType);
      verifications.push(verRes);
      this.db.recordVerification(verRes);

      // 5. 若状态为 STALE，生成 CAS 补丁提案
      if (verRes.status === 'STALE') {
        const patch = this.patchGen.generatePatch(verRes, cand.target_artifact_id, content, symbols);
        if (patch) {
          proposals.push(patch);
          this.db.recordPatchProposal(patch);
        }
      }
    }

    return {
      traceId,
      changeId,
      candidates,
      verifications,
      proposals
    };
  }

  public close() {
    this.db.close();
  }
}
