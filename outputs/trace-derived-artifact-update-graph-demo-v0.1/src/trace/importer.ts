import { readFileSync } from 'node:fs';
import { LedgerDb } from '../db/index.ts';
import type { IngestResult } from '../db/index.ts';
import type { ToolEvent } from '../types.ts';

export interface BatchIngestSummary {
  total: number;
  inserted: number;
  idempotentDuplicates: number;
  conflicts: number;
  rejected: number;
  results: IngestResult[];
}

export class TraceImporter {
  private db: LedgerDb;

  constructor(db: LedgerDb) {
    this.db = db;
  }

  /**
   * 导入 JSONL 格式的工具事件文件
   */
  public importJsonlFile(filePath: string): BatchIngestSummary {
    const rawContent = readFileSync(filePath, 'utf8');
    const lines = rawContent.split('\n').filter(line => line.trim().length > 0);

    const summary: BatchIngestSummary = {
      total: lines.length,
      inserted: 0,
      idempotentDuplicates: 0,
      conflicts: 0,
      rejected: 0,
      results: []
    };

    for (const line of lines) {
      try {
        const rawEvent = JSON.parse(line);
        const res = this.db.ingestToolEvent(rawEvent);
        summary.results.push(res);

        if (res.status === 'inserted') summary.inserted++;
        else if (res.status === 'idempotent_duplicate') summary.idempotentDuplicates++;
        else if (res.status === 'conflict') summary.conflicts++;
        else if (res.status === 'rejected') summary.rejected++;
      } catch (err: any) {
        summary.rejected++;
        summary.results.push({
          status: 'rejected',
          code: 'JSON_PARSE_ERROR',
          error: err.message
        });
      }
    }

    return summary;
  }
}
