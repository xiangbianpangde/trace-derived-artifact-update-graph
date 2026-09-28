import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { DaugBenchGenerator } from '../src/benchmark/dataset_generator.ts';
import {
  CochangeBaseline,
  StaticBaseline,
  SemanticBaseline,
  DaugModelRunner
} from '../src/benchmark/baselines.ts';

describe('Phase 1 基准数据集与对比基线自动化测试 (DAUG-Bench & Baselines)', () => {
  const generator = new DaugBenchGenerator();
  const cases = generator.generateBenchmarkSuite();

  test('基准数据集具备时间切分 (Temporal Split)，严格杜绝未来信息泄露 (No Data Leakage)', () => {
    assert.equal(cases.length, 3, '应包含 TS, Python, Go 三类代表性跨语言评测案例');

    for (const c of cases) {
      const splitTs = Date.parse(c.timestampSplit);
      const testTs = Date.parse(c.testChange.occurredAt);

      // 测试发生的变更必须严格晚于切分时刻
      assert.ok(testTs > splitTs, `Case ${c.caseId}: 测试变更时间必须 > 切分时间`);

      // 训练轨迹必须严格早于等于切分时刻
      for (const evt of c.trainEvents) {
        const evtTs = Date.parse(evt.occurred_at);
        assert.ok(evtTs <= splitTs, `Case ${c.caseId}: 训练事件时间必须 <= 切分时间`);
      }
    }
  });

  test('成功运行三大强非轨迹基线（时序共变更、静态调用图、语义检索）与 DAUG 完整模型', () => {
    const baselines = [
      new CochangeBaseline(),
      new StaticBaseline(),
      new SemanticBaseline(),
      new DaugModelRunner()
    ];

    for (const c of cases) {
      for (const runner of baselines) {
        const ranking = runner.rank(c);
        assert.ok(ranking.length > 0, `${runner.name} 在 Case ${c.caseId} 下必须输出候选排名`);

        // 验证得分降序排列
        for (let i = 0; i < ranking.length - 1; i++) {
          assert.ok(
            ranking[i].score >= ranking[i + 1].score,
            `${runner.name} 排名必须按得分降序`
          );
        }
      }
    }
  });

  test('DAUG 完整模型在跨语言场景下准确将失效文档排在首位 (Hit@1 = 100%)', () => {
    const daug = new DaugModelRunner();

    for (const c of cases) {
      const ranking = daug.rank(c);
      const top1 = ranking[0];

      // 验证 Top-1 命中 groundTruth 中的 staleArtifactIds
      assert.ok(
        c.groundTruth.staleArtifactIds.includes(top1.targetArtifactId),
        `Case ${c.caseId} (${c.language}): Top-1 必须命中真正失效的文档，实际为 ${top1.targetArtifactId}`
      );
    }
  });
});
