import { computeSha256 } from '../types.ts';
import type { ArtifactVersion } from '../types.ts';

export interface CasEntry {
  artifact_id: string;
  content: string;
  content_hash: string;
  observed_at: string;
  version_ref?: string;
}

export class CasRegistry {
  private versions: Map<string, CasEntry> = new Map();

  /**
   * 注册或更新制品的内容快照
   */
  public registerContent(artifactId: string, content: string, versionRef?: string): CasEntry {
    const content_hash = computeSha256(content);
    const entry: CasEntry = {
      artifact_id: artifactId,
      content,
      content_hash,
      observed_at: new Date().toISOString(),
      version_ref: versionRef
    };
    this.versions.set(artifactId, entry);
    return entry;
  }

  /**
   * 获取最新快照
   */
  public getLatest(artifactId: string): CasEntry | undefined {
    return this.versions.get(artifactId);
  }

  /**
   * CAS 校验：验证当前内容是否与预期哈希一致（防并发漂移，C07 核心保证）
   */
  public verifyHash(artifactId: string, expectedHash: string): { ok: boolean; currentHash?: string; code?: string } {
    const current = this.versions.get(artifactId);
    if (!current) {
      return { ok: false, code: 'ARTIFACT_NOT_FOUND' };
    }
    // 标准化哈希（去除可能的 sha256: 前缀）
    const cleanExpected = expectedHash.replace(/^sha256:/i, '').toLowerCase();
    const cleanCurrent = current.content_hash.toLowerCase();

    if (cleanExpected !== cleanCurrent) {
      return {
        ok: false,
        code: 'HASH_CONFLICT',
        currentHash: cleanCurrent
      };
    }
    return { ok: true, currentHash: cleanCurrent };
  }
}
