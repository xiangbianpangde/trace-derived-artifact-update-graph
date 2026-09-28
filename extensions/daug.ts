/**
 * DAUG (Trace-Derived Artifact Update Graph) — Pi Coding Agent Extension
 * ─────────────────────────────────────────────────────────────────────────────
 * Connects the Pi agent's real-time coding workflow with the DAUG dynamic
 * artifact update graph:
 *
 * 1. Automatic Live Trace Capture:
 *    Listens to Pi's `tool_execution_end` events (reads, edits, writes, bash commands)
 *    and appends them as behavioral edges to the SQLite ledger in real time.
 *
 * 2. Real-time Staleness Warning:
 *    When the agent or user edits code, DAUG checks the update graph. If any
 *    documentation or contracts become STALE, it notifies the developer in the UI
 *    and injects an update alert into the agent's context.
 *
 * 3. Agent Tools (`daug_check`, `daug_patch`):
 *    Allows the agent to proactively check which documents need updating and
 *    inspect/apply minimal patches with CAS hash protection.
 *
 * 4. Slash Command (`/daug`):
 *    Interactive command for developers in Pi TUI (`/daug check`, `/daug list`,
 *    `/daug show <id>`, `/daug apply <id>`, `/daug hook install`, `/daug status`).
 */

import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const execFileAsync = promisify(execFile);

const CANONICAL_DAUG_CLI = "/Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/bin/daug";
const LEDGER_SCHEMA_PROBE = `
import sqlite3
import sys
from pathlib import Path

try:
    db_path, repo_root = sys.argv[1:3]
    connection = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    required = {"repository", "artifact", "graph_snapshot"}
    if not required.issubset(tables):
        raise SystemExit(1)
    row = connection.execute("SELECT canonical_root FROM repository LIMIT 1").fetchone()
    if not row or Path(row[0]).resolve() != Path(repo_root).resolve():
        raise SystemExit(1)
except Exception:
    raise SystemExit(1)
`;

function resolveDaugCli(cwd: string): string {
	const candidates = [
		join(cwd, "bin/daug"),
		join(cwd, "../bin/daug"),
		CANONICAL_DAUG_CLI,
	];
	for (const p of candidates) {
		if (existsSync(p)) return p;
	}
	return "daug";
}

async function runDaug(cwd: string, args: string[]): Promise<{ stdout: string; stderr: string; code: number }> {
	const cli = resolveDaugCli(cwd);
	try {
		const { stdout, stderr } = await execFileAsync("python3", [cli, ...args], {
			cwd,
			maxBuffer: 10 * 1024 * 1024,
		});
		return { stdout: stdout.trim(), stderr: stderr.trim(), code: 0 };
	} catch (err: any) {
		return {
			stdout: err.stdout?.toString().trim() ?? "",
			stderr: err.stderr?.toString().trim() ?? (err.message || String(err)),
			code: typeof err.code === "number" ? err.code : 1,
		};
	}
}

async function isUsableDaugDb(dbPath: string, cwd: string): Promise<boolean> {
	try {
		await execFileAsync("python3", ["-c", LEDGER_SCHEMA_PROBE, resolve(dbPath), resolve(cwd)], {
			maxBuffer: 1024 * 1024,
		});
		return true;
	} catch {
		return false;
	}
}

async function findDaugDb(cwd: string): Promise<string | null> {
	const candidates = [
		join(cwd, ".daug.sqlite"),
		join(cwd, ".daug/ledger.sqlite"),
		join(cwd, "gap-demo.sqlite"),
		join(cwd, "demo.sqlite"),
		"/Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/gap-demo.sqlite",
		"/Users/xbpd/Documents/Codex/2026-09-14/referenced-chatgpt-conversation-this-is-an/demo.sqlite",
	];
	for (const c of candidates) {
		if (existsSync(c) && await isUsableDaugDb(c, cwd)) return c;
	}
	return null;
}

export default function daugExtension(pi: ExtensionAPI) {
	let enabled = true;
	const pendingAlerts: Array<{ file: string; staleDocs: string[] }> = [];

	// ─── Lifecycle & Status Indicator ──────────────────────────────────────────
	pi.on("session_start", async (_event, ctx) => {
		const db = await findDaugDb(ctx.cwd);
		if (db) {
			ctx.ui.setStatus("daug", "daug:on");
		}
	});

	// ─── Real-time Event Capture & Staleness Guard ─────────────────────────────
	pi.on("tool_execution_end", async (event, ctx) => {
		if (!enabled) return;
		const toolName = event.toolName;
		const params = (event.params as Record<string, unknown>) || {};
		const targetPath = (params.path || params.targetFile || params.target_file || params.file || params.filePath) as string | undefined;

		let op = "read";
		if (/edit/i.test(toolName)) op = "edit";
		else if (/write/i.test(toolName)) op = "write";
		else if (/search|grep|find/i.test(toolName)) op = "search";
		else if (/test/i.test(toolName)) op = "test";
		else if (/bash|exec/i.test(toolName)) op = "execute";

		// 1. Live trace event recording
		if (targetPath && typeof targetPath === "string") {
			runDaug(ctx.cwd, [
				"trace", "record",
				"--tool", toolName,
				"--op", op,
				"--path", targetPath,
				"--status", event.isError ? "failure" : "success",
				"--quiet",
			]).catch(() => {});
		}

		// 2. Staleness guard on code edits
		if ((op === "edit" || op === "write") && targetPath && typeof targetPath === "string") {
			const isCode = /\.(ts|tsx|js|jsx|py|go|rs|c|cpp|h|java)$/i.test(targetPath);
			if (isCode) {
				const checkRes = await runDaug(ctx.cwd, ["check", targetPath, "--json"]);
				if (checkRes.code === 0 && checkRes.stdout.startsWith("{")) {
					try {
						const data = JSON.parse(checkRes.stdout);
						if (data.total_stale > 0) {
							const staleList: string[] = [];
							for (const insp of data.inspections || []) {
								for (const c of insp.candidates || []) {
									if (c.status === "STALE" && c.target_uri) {
										staleList.push(c.target_uri);
									}
								}
							}
							if (staleList.length > 0) {
								ctx.ui.notify(
									`⚠️ [DAUG] Code edit in ${targetPath} made ${staleList.length} doc(s) stale:\n${staleList.map((d) => `  • ${d}`).join("\n")}`,
									"warning",
								);
								pendingAlerts.push({ file: targetPath, staleDocs: staleList });
							}
						}
					} catch {}
				}
			}
		}
	});

	// ─── Inject Context Alert into Agent Turn ──────────────────────────────────
	pi.on("before_agent_start", async (event) => {
		if (!enabled || pendingAlerts.length === 0) return;
		const alertSnippets = pendingAlerts.map(
			(a) => `• File '${a.file}' changed → Stale documentation: ${a.staleDocs.join(", ")}`,
		);
		pendingAlerts.length = 0; // Clear alerts

		const warningNotice = [
			"---",
			"[DAUG Artifact Staleness Notice]",
			"Your recent code modification has made related documentation or contracts stale in the update graph:",
			...alertSnippets,
			"Guidelines: Review the stale documents using the 'daug_check' or 'daug_patch' tool to keep documentation and code in sync.",
			"---",
		].join("\n");

		return {
			systemPrompt: `${event.systemPrompt}\n\n${warningNotice}`,
		};
	});

	// ─── Registered Tool: daug_check ───────────────────────────────────────────
	pi.registerTool({
		name: "daug_check",
		label: "DAUG Staleness Check",
		description:
			"Check if modified code files have caused related documentation, API contracts, or specifications to become stale. Uses the Trace-Derived Artifact Update Graph.",
		parameters: Type.Object({
			files: Type.Optional(
				Type.Array(Type.String(), {
					description: "Explicit list of code files to check. If omitted, checks all git staged/uncommitted files.",
				}),
			),
			staged: Type.Optional(
				Type.Boolean({
					description: "If true, checks only git staged changes.",
				}),
			),
			propose: Type.Optional(
				Type.Boolean({
					description: "If true, automatically generates minimal patch proposals for stale documents.",
				}),
			),
		}),
		async execute(_id, params, _signal, _onUpdate, ctx) {
			const args: string[] = ["check", "--json"];
			if (params.staged) args.push("--staged");
			if (params.propose ?? true) args.push("--propose");
			if (params.files && params.files.length > 0) {
				args.push("--files", ...params.files);
			}

			const res = await runDaug(ctx.cwd, args);
			if (res.code !== 0 && !res.stdout.startsWith("{")) {
				return {
					content: [{ type: "text", text: `DAUG check failed:\n${res.stderr || res.stdout}` }],
					details: { error: true, exit_code: res.code },
				};
			}

			try {
				const data = JSON.parse(res.stdout);
				if (data.error) {
					return {
						content: [{ type: "text", text: `DAUG check unavailable (exit ${data.exit_code ?? res.code}): ${data.error}` }],
						details: { ...data, error: true },
					};
				}
				if (data.status === "clean") {
					return {
						content: [{ type: "text", text: `### 📊 DAUG Documentation Staleness Report\n\n✅ ${data.message || "No modified files detected."}` }],
						details: data,
					};
				}
				let markdown = `### 📊 DAUG Documentation Staleness Report\n\n`;
				markdown += `**Database**: \`${data.database ?? "unknown"}\` | **Graph Version**: \`${data.graph_version ?? "unknown"}\`\n\n`;
				markdown += `**Summary**: Inspected **${data.total_files ?? 0}** file(s), found **${data.total_stale ?? 0}** stale document(s).\n\n`;

				for (const insp of data.inspections || []) {
					markdown += `#### File: \`${insp.file}\`\n`;
					const stale = (insp.candidates || []).filter((c: any) => c.status === "STALE");
					if (stale.length === 0) {
						markdown += `  - ✅ No stale documents detected.\n`;
					} else {
						for (const sc of stale) {
							markdown += `  - ⚠️ **[STALE]** \`${sc.target_uri}\` (Confidence: ${sc.confidence})\n`;
							for (const sp of sc.spans || []) {
								markdown += `    - \`${sp.locator}\`: ${sp.reason_code}\n`;
							}
							if (sc.patch) {
								markdown += `    - 💡 Proposed Patch: \`${sc.patch.patch_id}\` (Run \`daug_patch(action='show', patch_id='${sc.patch.patch_id}')\` to inspect diff)\n`;
							}
						}
					}
				}

				return {
					content: [{ type: "text", text: markdown }],
					details: data,
				};
			} catch (e: any) {
				return {
					content: [{ type: "text", text: res.stdout || res.stderr }],
					details: { raw: res.stdout },
				};
			}
		},
	});

	// ─── Registered Tool: daug_patch ───────────────────────────────────────────
	pi.registerTool({
		name: "daug_patch",
		label: "DAUG Patch Manager",
		description:
			"Inspect, list, or apply proposed documentation patches. Enforces Content-Addressed Storage (CAS) verification to prevent out-of-band overwrite drift.",
		parameters: Type.Object({
			action: Type.String({
				description: "Action to perform: 'list' to list proposed patches, 'show' to view diff, 'apply' to apply patch.",
			}),
			patch_id: Type.Optional(
				Type.String({
					description: "The patch ID to inspect or apply (required for 'show' and 'apply').",
				}),
			),
			confirm: Type.Optional(
				Type.Boolean({
					description: "Set to true to confirm application of the patch to disk. Prevents unintended writebacks.",
				}),
			),
		}),
		async execute(_id, params, _signal, _onUpdate, ctx) {
			const action = String(params.action || "list").toLowerCase();

			if (action === "list") {
				const res = await runDaug(ctx.cwd, ["patch", "list"]);
				return {
					content: [{ type: "text", text: res.stdout || "No patch proposals found." }],
					details: { stdout: res.stdout },
				};
			}

			if (action === "show") {
				if (!params.patch_id) {
					return { content: [{ type: "text", text: "Error: patch_id is required for action 'show'." }], details: { error: true } };
				}
				const res = await runDaug(ctx.cwd, ["patch", "show", params.patch_id]);
				return {
					content: [{ type: "text", text: `\`\`\`diff\n${res.stdout}\n\`\`\`` }],
					details: { diff: res.stdout },
				};
			}

			if (action === "apply") {
				if (!params.patch_id) {
					return { content: [{ type: "text", text: "Error: patch_id is required for action 'apply'." }], details: { error: true } };
				}
				if (!params.confirm) {
					return {
						content: [{
							type: "text",
							text: `⚠️ Human confirmation required: To apply patch '${params.patch_id}', pass confirm=true to verify you intend to write to disk.`,
						}],
						details: { confirmed: false },
					};
				}
				const res = await runDaug(ctx.cwd, ["patch", "apply", params.patch_id, "--yes"]);
				return {
					content: [{ type: "text", text: res.stdout || res.stderr }],
					details: { success: res.code === 0 },
				};
			}

			return {
				content: [{ type: "text", text: `Unknown action: ${action}. Use 'list', 'show', or 'apply'.` }],
				details: { error: true },
			};
		},
	});

	// ─── Registered Command: /daug ─────────────────────────────────────────────
	pi.registerCommand("daug", {
		description: "Trace-Derived Artifact Update Graph. Usage: /daug [check|list|show <id>|apply <id>|hook|status|on|off]",
		getArgumentCompletions: (prefix) => {
			const subcommands = [
				{ value: "check", label: "check — Inspect staged/modified code against doc update graph" },
				{ value: "list", label: "list — List pending patch proposals" },
				{ value: "show", label: "show <patch_id> — View Unified Diff of a patch proposal" },
				{ value: "apply", label: "apply <patch_id> — Safely apply patch with CAS verification" },
				{ value: "hook install", label: "hook install — Install git pre-commit staleness check hook" },
				{ value: "hook uninstall", label: "hook uninstall — Uninstall git pre-commit hook" },
				{ value: "review", label: "review — Launch interactive Web Review Dashboard (P2 deployment)" },
				{ value: "status", label: "status — Display DAUG database and graph snapshot info" },
				{ value: "on", label: "on — Enable DAUG live monitoring for this session" },
				{ value: "off", label: "off — Disable DAUG live monitoring for this session" },
			];
			const p = prefix.trim().toLowerCase();
			return subcommands.filter((s) => s.value.startsWith(p) || s.label.toLowerCase().includes(p));
		},
		handler: async (args, ctx) => {
			const tokens = (args ?? "").trim().split(/\s+/).filter(Boolean);
			const sub = (tokens[0] ?? "status").toLowerCase();

			if (sub === "on") {
				enabled = true;
				ctx.ui.setStatus("daug", "daug:on");
				ctx.ui.notify("DAUG live monitoring enabled.", "info");
				return;
			}
			if (sub === "off") {
				enabled = false;
				ctx.ui.setStatus("daug", "daug:off");
				ctx.ui.notify("DAUG live monitoring disabled.", "info");
				return;
			}

			if (sub === "check") {
				const files = tokens.slice(1);
				ctx.ui.notify("Running DAUG staleness check…", "info");
				const checkArgs = ["check"];
				if (files.length > 0) checkArgs.push("--files", ...files);
				else checkArgs.push("--staged");
				const res = await runDaug(ctx.cwd, checkArgs);
				ctx.ui.notify(res.stdout || res.stderr, res.code === 0 ? "info" : "warning");
				return;
			}

			if (sub === "list") {
				const res = await runDaug(ctx.cwd, ["patch", "list"]);
				ctx.ui.notify(res.stdout || "No patch proposals found.", "info");
				return;
			}

			if (sub === "show") {
				const patchId = tokens[1];
				if (!patchId) {
					ctx.ui.notify("Usage: /daug show <patch_id>", "error");
					return;
				}
				const res = await runDaug(ctx.cwd, ["patch", "show", patchId]);
				if (res.code !== 0) {
					ctx.ui.notify(`Error: ${res.stderr || res.stdout}`, "error");
					return;
				}
				ctx.ui.notify(`Patch Diff (${patchId}):\n${res.stdout}`, "info");
				return;
			}

			if (sub === "apply") {
				const patchId = tokens[1];
				if (!patchId) {
					ctx.ui.notify("Usage: /daug apply <patch_id>", "error");
					return;
				}
				const diffRes = await runDaug(ctx.cwd, ["patch", "show", patchId]);
				if (diffRes.code !== 0) {
					ctx.ui.notify(`Error finding patch: ${diffRes.stderr || diffRes.stdout}`, "error");
					return;
				}

				const res = await runDaug(ctx.cwd, ["patch", "apply", patchId, "--yes"]);
				if (res.code === 0) {
					ctx.ui.notify(`✅ Applied patch ${patchId}:\n${res.stdout}`, "info");
				} else {
					ctx.ui.notify(`❌ Failed to apply patch:\n${res.stderr || res.stdout}`, "error");
				}
				return;
			}

			if (sub === "hook") {
				const action = tokens[1] ?? "install";
				const res = await runDaug(ctx.cwd, ["hook", action]);
				ctx.ui.notify(res.stdout || res.stderr, res.code === 0 ? "info" : "error");
				return;
			}

			if (sub === "review") {
				const port = tokens[1] ?? "8484";
				ctx.ui.notify(`Launching DAUG Web Review Dashboard on http://127.0.0.1:${port}/ ...`, "info");
				runDaug(ctx.cwd, ["review", "--port", port]);
				return;
			}

			// Default: status
			const db = await findDaugDb(ctx.cwd);
			const cli = resolveDaugCli(ctx.cwd);
			ctx.ui.notify(
				`DAUG Extension Status:\n` +
				`  • Monitoring: ${enabled ? "ACTIVE (on)" : "DISABLED (off)"}\n` +
				`  • CLI Path: ${cli}\n` +
				`  • Database: ${db ?? "Not found (run 'daug init' to initialize)"}\n` +
				`  • Commands: /daug [check|list|show|apply|hook|status]`,
				"info",
			);
		},
	});
}
