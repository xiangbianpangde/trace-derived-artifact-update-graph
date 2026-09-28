import { computeSha256 } from '../types.ts';
import type { ToolEvent } from '../types.ts';

export interface ValidationSuccess {
  ok: true;
  event: ToolEvent;
  digest: string;
}

export interface ValidationFailure {
  ok: false;
  code: string;
  error: string;
  details?: Record<string, unknown>;
}

export type ValidationOutcome = ValidationSuccess | ValidationFailure;

const SHA256_REGEX = /^(?:sha256:)?[0-9a-f]{64}$/i;

export class EventValidator {
  /**
   * 严格校验工具事件的合法性（覆盖 C03、C04、C05 等规则）
   */
  public static validateEvent(raw: unknown): ValidationOutcome {
    if (!raw || typeof raw !== 'object') {
      return { ok: false, code: 'INVALID_OBJECT', error: 'Event must be a non-null object' };
    }

    const e = raw as Partial<ToolEvent>;

    // 1. 必填基础字段
    if (e.schema_version !== 'daug.tool-event.v1') {
      return { ok: false, code: 'INVALID_SCHEMA_VERSION', error: 'schema_version must be daug.tool-event.v1' };
    }
    if (!e.event_id || typeof e.event_id !== 'string' || e.event_id.length < 8) {
      return { ok: false, code: 'INVALID_EVENT_ID', error: 'event_id must be a string of at least 8 chars' };
    }
    if (!e.trace_id || typeof e.trace_id !== 'string' || e.trace_id.length < 8) {
      return { ok: false, code: 'INVALID_TRACE_ID', error: 'trace_id must be a string of at least 8 chars' };
    }
    if (!e.repository_id || typeof e.repository_id !== 'string') {
      return { ok: false, code: 'INVALID_REPO_ID', error: 'repository_id is required' };
    }
    if (typeof e.sequence_no !== 'number' || e.sequence_no < 0 || !Number.isInteger(e.sequence_no)) {
      return { ok: false, code: 'INVALID_SEQUENCE_NO', error: 'sequence_no must be a non-negative integer' };
    }
    if (!e.occurred_at || typeof e.occurred_at !== 'string' || Number.isNaN(Date.parse(e.occurred_at))) {
      return { ok: false, code: 'INVALID_OCCURRED_AT', error: 'occurred_at must be an ISO date-time string' };
    }

    const validOps = ['read', 'search', 'edit', 'write', 'delete', 'test', 'execute', 'commit', 'approve', 'reject'];
    if (!e.operation || !validOps.includes(e.operation)) {
      return { ok: false, code: 'INVALID_OPERATION', error: `operation must be one of ${validOps.join(', ')}` };
    }

    const validStatuses = ['success', 'failure', 'cancelled', 'unknown'];
    if (!e.result_status || !validStatuses.includes(e.result_status)) {
      return { ok: false, code: 'INVALID_RESULT_STATUS', error: `result_status must be one of ${validStatuses.join(', ')}` };
    }

    const validOrigins = ['organic', 'system_recommended', 'human_directed', 'replay', 'unknown'];
    if (!e.access_origin || !validOrigins.includes(e.access_origin)) {
      return { ok: false, code: 'INVALID_ACCESS_ORIGIN', error: `access_origin must be one of ${validOrigins.join(', ')}` };
    }

    // 2. C05 契约：推荐访问缺少 recommendation_id 时必须失败
    if (e.access_origin === 'system_recommended') {
      if (!e.recommendation_id || typeof e.recommendation_id !== 'string' || e.recommendation_id.trim() === '') {
        return {
          ok: false,
          code: 'RECOMMENDATION_ID_MISSING',
          error: 'access_origin is system_recommended but recommendation_id is missing or empty (Constraint C05)'
        };
      }
    }

    // 3. C03 契约：目标路径越过仓库根目录（路径穿越检查）
    if (e.artifact_path) {
      if (typeof e.artifact_path !== 'string') {
        return { ok: false, code: 'INVALID_PATH', error: 'artifact_path must be string' };
      }
      // 不得以 / 开头（必须相对路径），不得包含 ../ 或以 .. 结尾
      if (
        e.artifact_path.startsWith('/') ||
        e.artifact_path.startsWith('\\') ||
        e.artifact_path.split(/[/\\]/).includes('..') ||
        e.artifact_path.includes(':') // windows drive
      ) {
        return {
          ok: false,
          code: 'PATH_TRAVERSAL_DETECTED',
          error: `artifact_path ${e.artifact_path} violates repository root boundary (Constraint C03)`
        };
      }
    }

    // 4. C04 契约：编辑/修改类事件如果缺少前后哈希，标记 trace incomplete
    if (e.operation === 'edit' || e.operation === 'write') {
      if (e.result_status === 'success') {
        if (!e.before_hash || !e.after_hash) {
          return {
            ok: false,
            code: 'TRACE_INCOMPLETE_MISSING_HASHES',
            error: 'Edit/Write event succeeded but missing before_hash or after_hash (Constraint C04)'
          };
        }
        if (!SHA256_REGEX.test(e.before_hash) || !SHA256_REGEX.test(e.after_hash)) {
          return {
            ok: false,
            code: 'INVALID_HASH_FORMAT',
            error: 'before_hash or after_hash is not valid 64-char hex sha256'
          };
        }
      }
    }

    // 计算标准事件指纹（排除创建时间和自身 digest）
    const canonicalPayload = JSON.stringify({
      schema_version: e.schema_version,
      event_id: e.event_id,
      trace_id: e.trace_id,
      repository_id: e.repository_id,
      sequence_no: e.sequence_no,
      occurred_at: e.occurred_at,
      operation: e.operation,
      artifact_id: e.artifact_id || null,
      artifact_path: e.artifact_path || null,
      before_hash: e.before_hash || null,
      after_hash: e.after_hash || null,
      access_origin: e.access_origin,
      recommendation_id: e.recommendation_id || null,
      result_status: e.result_status,
      exit_code: e.exit_code ?? null,
      payload_policy: e.payload_policy || 'full'
    });

    const event_digest = computeSha256(canonicalPayload);

    const validatedEvent: ToolEvent = {
      schema_version: e.schema_version,
      event_id: e.event_id,
      trace_id: e.trace_id,
      repository_id: e.repository_id,
      sequence_no: e.sequence_no,
      occurred_at: e.occurred_at,
      operation: e.operation,
      result_status: e.result_status,
      access_origin: e.access_origin,
      collector_version: e.collector_version || '1.0.0',
      payload_policy: e.payload_policy || 'full',
      parent_event_id: e.parent_event_id ?? null,
      tool_name: e.tool_name ?? null,
      artifact_id: e.artifact_id ?? (e.artifact_path ? `art:${e.repository_id}:${e.artifact_path}` : null),
      artifact_path: e.artifact_path ?? null,
      target_selector: e.target_selector ?? null,
      input_digest: e.input_digest ?? null,
      output_digest: e.output_digest ?? null,
      before_hash: e.before_hash ?? null,
      after_hash: e.after_hash ?? null,
      diff_digest: e.diff_digest ?? null,
      exit_code: e.exit_code ?? null,
      recommendation_id: e.recommendation_id ?? null,
      event_digest,
      created_at: e.created_at || new Date().toISOString()
    };

    return { ok: true, event: validatedEvent, digest: event_digest };
  }
}
