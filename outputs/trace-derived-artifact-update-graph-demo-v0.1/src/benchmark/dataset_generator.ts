import { computeSha256 } from '../types.ts';
import type { ToolEvent, ChangeType } from '../types.ts';

export interface BenchmarkArtifact {
  artifactId: string;
  repoId: string;
  path: string;
  kind: 'source_code' | 'test' | 'design_doc' | 'config' | 'api_contract';
  content: string;
}

export interface BenchmarkCase {
  caseId: string;
  repoId: string;
  language: 'typescript' | 'python' | 'go';
  timestampSplit: string; // 严格的时间切分点 t_split
  trainEvents: ToolEvent[]; // t <= t_split 的训练/历史轨迹 (禁止未来泄露)
  testChange: {
    sourceArtifactId: string;
    diffText: string;
    changeType: ChangeType;
    occurredAt: string; // t > t_split
  };
  artifacts: BenchmarkArtifact[];
  groundTruth: {
    staleArtifactIds: string[];
    validArtifactIds: string[];
    mustReviewArtifactIds: string[];
  };
}

export class DaugBenchGenerator {
  /**
   * 生成包含跨语言、时间切分的标准评测数据集 (DAUG-Bench)
   */
  public generateBenchmarkSuite(): BenchmarkCase[] {
    const cases: BenchmarkCase[] = [];

    // Case 1: TypeScript / Web 架构 - 用户会话重构 (TS)
    cases.push(this.generateTsSessionCase());

    // Case 2: Python / 数据服务架构 - 数据模型字段弃用 (Python)
    cases.push(this.generatePythonModelCase());

    // Case 3: Go / 微服务架构 - gRPC 鉴权拦截器接口修改 (Go)
    cases.push(this.generateGoMicroserviceCase());

    return cases;
  }

  private generateTsSessionCase(): BenchmarkCase {
    const repoId = 'repo-ts-session';
    const splitTime = '2026-09-20T00:00:00.000Z';

    const artifacts: BenchmarkArtifact[] = [
      {
        artifactId: 'art:session_mgr',
        repoId,
        path: 'src/session/manager.ts',
        kind: 'source_code',
        content: `export interface SessionData { session_token: string; expire_at: number; }\n`
      },
      {
        artifactId: 'art:session_test',
        repoId,
        path: 'tests/session.test.ts',
        kind: 'test',
        content: `import { SessionData } from '../src/session/manager';\n`
      },
      {
        artifactId: 'art:session_doc',
        repoId,
        path: 'docs/session_design.md',
        kind: 'design_doc',
        content: `# Session 管理规范\n客户端携带 session_token 进行状态校验。\n`
      },
      {
        artifactId: 'art:unrelated_util',
        repoId,
        path: 'src/utils/math.ts',
        kind: 'source_code',
        content: `export function add(a: number, b: number) { return a + b; }\n`
      }
    ];

    // 训练历史事件 (发生在 splitTime 之前，建立正常的读写与协同轨迹)
    const trainEvents: ToolEvent[] = [
      {
        schema_version: 'daug.tool-event.v1',
        event_id: 'evt_ts_001',
        trace_id: 'trc_ts_hist_1',
        repository_id: repoId,
        sequence_no: 1,
        occurred_at: '2026-09-18T10:00:00.000Z',
        operation: 'read',
        result_status: 'success',
        access_origin: 'organic',
        collector_version: '1.0.0',
        payload_policy: 'full',
        artifact_id: 'art:session_mgr',
        artifact_path: 'src/session/manager.ts'
      },
      {
        schema_version: 'daug.tool-event.v1',
        event_id: 'evt_ts_002',
        trace_id: 'trc_ts_hist_1',
        repository_id: repoId,
        sequence_no: 2,
        occurred_at: '2026-09-18T10:01:00.000Z',
        operation: 'read',
        result_status: 'success',
        access_origin: 'organic',
        collector_version: '1.0.0',
        payload_policy: 'full',
        artifact_id: 'art:session_doc',
        artifact_path: 'docs/session_design.md'
      }
    ];

    return {
      caseId: 'case_ts_01_session_token_rename',
      repoId,
      language: 'typescript',
      timestampSplit: splitTime,
      trainEvents,
      testChange: {
        sourceArtifactId: 'art:session_mgr',
        diffText: `--- a/src/session/manager.ts
+++ b/src/session/manager.ts
@@ -1,2 +1,2 @@
- export interface SessionData { session_token: string; expire_at: number; }
+ export interface SessionData { bearer_token: string; expire_at: number; }
`,
        changeType: 'interface',
        occurredAt: '2026-09-22T14:00:00.000Z' // 严格在 splitTime 之后
      },
      artifacts,
      groundTruth: {
        staleArtifactIds: ['art:session_doc'], // session_token 改为 bearer_token 使文档陈旧
        validArtifactIds: ['art:unrelated_util'],
        mustReviewArtifactIds: ['art:session_doc', 'art:session_test']
      }
    };
  }

  private generatePythonModelCase(): BenchmarkCase {
    const repoId = 'repo-py-analytics';
    const splitTime = '2026-09-20T00:00:00.000Z';

    const artifacts: BenchmarkArtifact[] = [
      {
        artifactId: 'art:py_model',
        repoId,
        path: 'analytics/models/user_event.py',
        kind: 'source_code',
        content: `class UserEvent:\n    def __init__(self, tenant_id: str):\n        self.tenant_id = tenant_id\n`
      },
      {
        artifactId: 'art:py_doc',
        repoId,
        path: 'docs/analytics_schema.md',
        kind: 'design_doc',
        content: `# 数据湖事件格式\n上报载荷必须携带 tenant_id 以便多租户分表。\n`
      },
      {
        artifactId: 'art:py_cfg',
        repoId,
        path: 'config/pipeline.yaml',
        kind: 'config',
        content: `partition_key: tenant_id\n`
      }
    ];

    const trainEvents: ToolEvent[] = [
      {
        schema_version: 'daug.tool-event.v1',
        event_id: 'evt_py_001',
        trace_id: 'trc_py_hist_1',
        repository_id: repoId,
        sequence_no: 1,
        occurred_at: '2026-09-17T09:00:00.000Z',
        operation: 'read',
        result_status: 'success',
        access_origin: 'organic',
        collector_version: '1.0.0',
        payload_policy: 'full',
        artifact_id: 'art:py_model',
        artifact_path: 'analytics/models/user_event.py'
      },
      {
        schema_version: 'daug.tool-event.v1',
        event_id: 'evt_py_002',
        trace_id: 'trc_py_hist_1',
        repository_id: repoId,
        sequence_no: 2,
        occurred_at: '2026-09-17T09:03:00.000Z',
        operation: 'read',
        result_status: 'success',
        access_origin: 'organic',
        collector_version: '1.0.0',
        payload_policy: 'full',
        artifact_id: 'art:py_doc',
        artifact_path: 'docs/analytics_schema.md'
      }
    ];

    return {
      caseId: 'case_py_02_tenant_id_to_workspace_id',
      repoId,
      language: 'python',
      timestampSplit: splitTime,
      trainEvents,
      testChange: {
        sourceArtifactId: 'art:py_model',
        diffText: `--- a/analytics/models/user_event.py
+++ b/analytics/models/user_event.py
@@ -1,2 +1,2 @@
- class UserEvent: tenant_id: str
+ class UserEvent: workspace_id: str
`,
        changeType: 'schema',
        occurredAt: '2026-09-24T11:00:00.000Z'
      },
      artifacts,
      groundTruth: {
        staleArtifactIds: ['art:py_doc'],
        validArtifactIds: [],
        mustReviewArtifactIds: ['art:py_doc', 'art:py_cfg']
      }
    };
  }

  private generateGoMicroserviceCase(): BenchmarkCase {
    const repoId = 'repo-go-auth';
    const splitTime = '2026-09-20T00:00:00.000Z';

    const artifacts: BenchmarkArtifact[] = [
      {
        artifactId: 'art:go_interceptor',
        repoId,
        path: 'pkg/auth/interceptor.go',
        kind: 'source_code',
        content: `type AuthContext struct { account_key string }\n`
      },
      {
        artifactId: 'art:go_contract',
        repoId,
        path: 'proto/v1/auth.proto',
        kind: 'api_contract',
        content: `message AuthRequest { string account_key = 1; }\n`
      },
      {
        artifactId: 'art:go_runbook',
        repoId,
        path: 'docs/runbook_auth.md',
        kind: 'design_doc',
        content: `# 鉴权排障手册\n如果遇到 401，请检查客户端的 account_key 配置。\n`
      }
    ];

    const trainEvents: ToolEvent[] = [
      {
        schema_version: 'daug.tool-event.v1',
        event_id: 'evt_go_001',
        trace_id: 'trc_go_hist_1',
        repository_id: repoId,
        sequence_no: 1,
        occurred_at: '2026-09-19T08:00:00.000Z',
        operation: 'read',
        result_status: 'success',
        access_origin: 'organic',
        collector_version: '1.0.0',
        payload_policy: 'full',
        artifact_id: 'art:go_interceptor',
        artifact_path: 'pkg/auth/interceptor.go'
      },
      {
        schema_version: 'daug.tool-event.v1',
        event_id: 'evt_go_002',
        trace_id: 'trc_go_hist_1',
        repository_id: repoId,
        sequence_no: 2,
        occurred_at: '2026-09-19T08:02:00.000Z',
        operation: 'read',
        result_status: 'success',
        access_origin: 'organic',
        collector_version: '1.0.0',
        payload_policy: 'full',
        artifact_id: 'art:go_runbook',
        artifact_path: 'docs/runbook_auth.md'
      }
    ];

    return {
      caseId: 'case_go_03_account_key_rename',
      repoId,
      language: 'go',
      timestampSplit: splitTime,
      trainEvents,
      testChange: {
        sourceArtifactId: 'art:go_interceptor',
        diffText: `--- a/pkg/auth/interceptor.go
+++ b/pkg/auth/interceptor.go
@@ -1,1 +1,1 @@
- type AuthContext struct { account_key string }
+ type AuthContext struct { principal_key string }
`,
        changeType: 'interface',
        occurredAt: '2026-09-25T16:00:00.000Z'
      },
      artifacts,
      groundTruth: {
        staleArtifactIds: ['art:go_runbook'],
        validArtifactIds: [],
        mustReviewArtifactIds: ['art:go_runbook', 'art:go_contract']
      }
    };
  }
}
