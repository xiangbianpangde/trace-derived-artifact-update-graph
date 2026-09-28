#!/usr/bin/env node
import { DaugEngine } from './engine.ts';
import { runFullEvaluationAndGenerateReport } from '../scripts/run_evaluation.ts';
import { join } from 'node:path';

function printHelp() {
  console.log(`
DAUG (Trace-Derived Artifact Update Graph) CLI - v0.1.0

用法:
  node --experimental-strip-types src/cli.ts <command> [options]

命令:
  check     运行默认示例仓库检查，执行候选召回与陈旧验证
  eval      运行 Phase 1 跨仓库基准评测并生成消融实验报告
  help      显示此帮助信息
`);
}

async function main() {
  const args = process.argv.slice(2);
  const cmd = args[0] || 'help';

  if (cmd === 'eval') {
    console.log('正在执行 Phase 1 跨语言时间切分消融评测...');
    const report = runFullEvaluationAndGenerateReport();
    console.log('评测完成！报告已保存至 reports/phase1_benchmark_evaluation_report.md');
    console.log('\n--- 核心指标摘要 ---');
    const tableMatch = report.match(/\| 候选召回模型[\s\S]*?(?=\n\n---)/);
    if (tableMatch) {
      console.log(tableMatch[0]);
    }
  } else if (cmd === 'check') {
    console.log('正在运行 DAUG 示例流水线 (Demo Pipeline)...');
    const engine = new DaugEngine(':memory:');
    const tracePath = join(process.cwd(), 'examples', 'demo_trace.jsonl');
    const importRes = engine.importTraceFile(tracePath);
    console.log(`成功导入事件: ${importRes.inserted} 条`);

    const contents = new Map<string, string>();
    contents.set(
      'artifact-doc-auth-design',
      '# 认证系统架构\n系统在每次请求时读取 user_id 并做白名单校验。\n'
    );
    const diff = `--- a/src/auth/user_context.ts
+++ b/src/auth/user_context.ts
@@ -5,1 +5,1 @@
- export interface UserContext { user_id: string; }
+ export interface UserContext { subject_id: string; }
`;

    const res = engine.runPipeline(
      'trace-demo-interface-001',
      'artifact-src-user-context',
      diff,
      'interface',
      contents
    );

    console.log(`召回候选数量: ${res.candidates.length}`);
    for (const c of res.candidates) {
      const v = res.verifications.find(x => x.candidate_id === c.candidate_id);
      console.log(`  - 候选 [Rank ${c.rank}]: ${c.target_artifact_id} | 得分: ${c.score} | 判定: ${v?.status}`);
    }
    console.log(`提出补丁数量: ${res.proposals.length}`);
    for (const p of res.proposals) {
      console.log(`  - 补丁 ID: ${p.patch_id} | 目标: ${p.target_artifact_id} | 最小性: ${p.minimality_check}`);
    }
    engine.close();
  } else {
    printHelp();
  }
}

main().catch(err => {
  console.error('DAUG CLI 运行失败:', err);
  process.exit(1);
});
