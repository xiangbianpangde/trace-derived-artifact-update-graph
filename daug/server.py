"""
daug.server - Lightweight interactive Web Review Server for DAUG (Human-in-the-Loop P2 Deployment).

Provides:
- Embedded Single Page Application (SPA) with Split-Diff inspection.
- Real-time Git & DAUG staleness check endpoint.
- One-Click CAS-Guarded patch application with instant readback verification.
- Rejection and abstention controls.
- Zero npm/pip dependencies: pure Python standard library.
"""

import json
import os
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from daug.ledger import Ledger
from daug.patcher import HashConflictError, PatchProposer
from daug.retriever import CandidateRetriever
from daug.verifier import StalenessVerifier

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>DAUG Review Dashboard - 人机协同文档审查工作台</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --danger: #ef4444;
      --success: #10b981;
      --warning: #f59e0b;
      --diff-add: #064e3b;
      --diff-add-text: #a7f3d0;
      --diff-del: #7f1d1d;
      --diff-del-text: #fecaca;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
    .header h1 { font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
    .badge { padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; text-transform: uppercase; }
    .badge-p2 { background: #3b82f633; color: #60a5fa; border: 1px solid #3b82f666; }
    .btn { background: var(--accent); color: white; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 13px; transition: background 0.15s; }
    .btn:hover { background: var(--accent-hover); }
    .btn-success { background: var(--success); }
    .btn-success:hover { background: #059669; }
    .btn-danger { background: #dc2626; }
    .btn-danger:hover { background: #b91c1c; }
    .btn-secondary { background: var(--border); color: var(--text); }
    .btn-secondary:hover { background: #475569; }
    .grid { display: grid; grid-template-columns: 360px 1fr; gap: 24px; height: calc(100vh - 120px); }
    .sidebar { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .main-view { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; }
    .section-title { font-size: 12px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
    .card { background: #0f172a88; border: 1px solid var(--border); border-radius: 6px; padding: 12px; cursor: pointer; transition: all 0.15s; }
    .card:hover { border-color: var(--accent); }
    .card.active { border-color: var(--accent); background: #1e3a8a33; }
    .card-title { font-size: 13px; font-weight: 600; margin-bottom: 4px; display: flex; justify-content: space-between; align-items: center; }
    .card-meta { font-size: 11px; color: var(--text-muted); }
    .diff-container { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; background: #0b0f19; border: 1px solid var(--border); border-radius: 6px; overflow-x: auto; padding: 12px; flex: 1; white-space: pre; }
    .diff-line-add { background: var(--diff-add); color: var(--diff-add-text); display: block; padding: 1px 4px; }
    .diff-line-del { background: var(--diff-del); color: var(--diff-del-text); display: block; padding: 1px 4px; }
    .diff-line-info { color: #38bdf8; display: block; padding: 1px 4px; font-weight: bold; }
    .action-bar { display: flex; justify-content: space-between; align-items: center; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
    .toast { position: fixed; bottom: 24px; right: 24px; background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px; padding: 12px 20px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.5); display: none; }
    .toast.show { display: block; }
  </style>
</head>
<body>
  <div class="header">
    <h1>
      <span>DAUG Review Workbench</span>
      <span class="badge badge-p2">P2 Assisted Deployment</span>
    </h1>
    <div style="display: flex; gap: 8px; align-items: center;">
      <span id="status-indicator" style="font-size: 12px; color: var(--text-muted);">Ready</span>
      <button class="btn btn-secondary" onclick="loadInspection()">Refresh Check</button>
    </div>
  </div>

  <div class="grid">
    <div class="sidebar">
      <div class="section-title">Stale Document Proposals (<span id="stale-count">0</span>)</div>
      <div id="stale-list" style="display: flex; flex-direction: column; gap: 8px;">
        <div style="color: var(--text-muted); font-size: 12px;">Loading inspection...</div>
      </div>
    </div>

    <div class="main-view">
      <div id="diff-header" style="margin-bottom: 16px;">
        <h2 id="diff-title" style="font-size: 16px; font-weight: 600;">Select a proposal to review</h2>
        <p id="diff-desc" style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Click an item from the left panel to inspect affected claim anchors and Unified Diff.</p>
      </div>

      <div id="diff-body" class="diff-container">// Diff payload will appear here</div>

      <div class="action-bar" id="action-bar" style="display: none;">
        <div>
          <span style="font-size: 12px; color: var(--text-muted);">Expected Hash: </span>
          <code id="expected-hash" style="font-size: 11px; background: #000; padding: 2px 6px; border-radius: 4px;">...</code>
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="btn btn-secondary" onclick="rejectSelectedPatch()">Reject Proposal</button>
          <button class="btn btn-success" onclick="applySelectedPatch()">Apply Patch (CAS-Guarded)</button>
        </div>
      </div>
    </div>
  </div>

  <div id="toast" class="toast">Action completed</div>

  <script>
    let currentData = null;
    let selectedPatchId = null;

    async function loadInspection() {
      document.getElementById('status-indicator').innerText = 'Inspecting...';
      try {
        const res = await fetch('/api/check');
        const data = await res.json();
        currentData = data;
        renderSidebar(data);
        document.getElementById('status-indicator').innerText = 'Up to date';
      } catch (err) {
        document.getElementById('status-indicator').innerText = 'Check error';
        showToast('Failed to load check: ' + err.message);
      }
    }

    function renderSidebar(data) {
      const listEl = document.getElementById('stale-list');
      listEl.innerHTML = '';
      let proposals = [];

      (data.inspections || []).forEach(insp => {
        (insp.candidates || []).forEach(cand => {
          if (cand.status === 'STALE' && cand.patch) {
            proposals.push({
              patch_id: cand.patch.patch_id,
              target_uri: cand.target_uri,
              confidence: cand.confidence,
              spans: cand.spans || [],
              source_file: insp.file,
              diff: cand.patch.diff || ''
            });
          }
        });
      });

      document.getElementById('stale-count').innerText = proposals.length;

      if (proposals.length === 0) {
        listEl.innerHTML = '<div style="color: #10b981; font-size: 13px; padding: 12px;">✅ All documentation and contracts are verified consistent with code changes!</div>';
        document.getElementById('action-bar').style.display = 'none';
        document.getElementById('diff-body').innerText = '// No pending patches required.';
        return;
      }

      proposals.forEach((p, idx) => {
        const card = document.createElement('div');
        card.className = 'card' + (p.patch_id === selectedPatchId ? ' active' : '');
        card.onclick = () => selectProposal(p);
        card.innerHTML = `
          <div class="card-title">
            <span>${p.target_uri}</span>
            <span class="badge badge-p2">${Math.round(p.confidence * 100)}% Conf</span>
          </div>
          <div class="card-meta">Caused by: <code>${p.source_file}</code></div>
          <div class="card-meta" style="margin-top: 4px; color: #cbd5e1;">Spans: ${p.spans.length} anchor(s)</div>
        `;
        listEl.appendChild(card);
        if (idx === 0 && !selectedPatchId) {
          selectProposal(p);
        }
      });
    }

    function selectProposal(p) {
      selectedPatchId = p.patch_id;
      document.querySelectorAll('.card').forEach(el => el.classList.remove('active'));
      event && event.currentTarget && event.currentTarget.classList.add('active');

      document.getElementById('diff-title').innerText = p.target_uri;
      document.getElementById('diff-desc').innerText = `Patch ID: ${p.patch_id} | ${p.spans.map(s => s.locator).join(', ')}`;
      document.getElementById('expected-hash').innerText = p.patch_id.slice(0, 16) + '...';
      document.getElementById('action-bar').style.display = 'flex';

      // Render colored diff
      const body = document.getElementById('diff-body');
      body.innerHTML = '';
      (p.diff || '').split('\\n').forEach(line => {
        const span = document.createElement('span');
        if (line.startsWith('+') && !line.startsWith('+++')) {
          span.className = 'diff-line-add';
        } else if (line.startswith('-') && !line.startsWith('---')) {
          span.className = 'diff-line-del';
        } else if (line.startsWith('@@')) {
          span.className = 'diff-line-info';
        }
        span.innerText = line;
        body.appendChild(span);
        body.appendChild(document.createTextNode('\\n'));
      });
    }

    async function applySelectedPatch() {
      if (!selectedPatchId) return;
      try {
        const res = await fetch('/api/patch/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch_id: selectedPatchId })
        });
        const result = await res.json();
        if (result.success) {
          showToast('✅ Applied patch successfully: ' + result.receipt_id);
          selectedPatchId = null;
          loadInspection();
        } else {
          showToast('❌ Failed: ' + (result.error || 'Unknown error'));
        }
      } catch (err) {
        showToast('❌ Error: ' + err.message);
      }
    }

    async function rejectSelectedPatch() {
      if (!selectedPatchId) return;
      try {
        const res = await fetch('/api/patch/reject', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ patch_id: selectedPatchId })
        });
        const result = await res.json();
        showToast('Proposal rejected');
        selectedPatchId = null;
        loadInspection();
      } catch (err) {
        showToast('❌ Error: ' + err.message);
      }
    }

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.className = 'toast show';
      setTimeout(() => { t.className = 'toast'; }, 3500);
    }

    window.onload = loadInspection;
  </script>
</body>
</html>
"""

class DaugReviewHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, repo_root: Path, db_path: Path, **kwargs):
        self.repo_root = repo_root
        self.db_path = db_path
        super().__init__(*args, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(INDEX_HTML.encode("utf-8"))
        elif parsed.path == "/api/check":
            self.handle_api_check()
        elif parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "running", "repo_root": str(self.repo_root)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if parsed.path == "/api/patch/apply":
            self.handle_api_apply(payload)
        elif parsed.path == "/api/patch/reject":
            self.handle_api_reject(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_api_check(self):
        ledger = Ledger(str(self.db_path))
        retriever = CandidateRetriever(ledger, minimum_score=0.10)
        verifier = StalenessVerifier(ledger, repo_root_override=self.repo_root)
        patcher = PatchProposer(ledger, repo_root_override=self.repo_root)

        # Detect git diff
        changed_files = []
        try:
            res = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, cwd=str(self.repo_root)
            )
            changed_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            pass

        # If clean, check staged or fallback to top source artifacts in DB for demo inspection
        if not changed_files:
            try:
                res_staged = subprocess.run(
                    ["git", "diff", "--name-only", "--cached"],
                    capture_output=True, text=True, cwd=str(self.repo_root)
                )
                changed_files = [line.strip() for line in res_staged.stdout.splitlines() if line.strip()]
            except Exception:
                pass

        if not changed_files:
            # Fallback for demo review preview: check active change events in DB
            rows = ledger.conn.execute("SELECT a.canonical_uri FROM change_event ce JOIN artifact a ON ce.source_artifact_id = a.artifact_id LIMIT 3").fetchall()
            changed_files = [r[0] for r in rows]

        inspections = []
        for f in changed_files:
            art_row = ledger.conn.execute("SELECT artifact_id FROM artifact WHERE canonical_uri LIKE ? LIMIT 1", (f"%{f}",)).fetchone()
            if not art_row:
                continue
            aid = art_row[0]
            change_row = ledger.conn.execute("SELECT change_id FROM change_event WHERE source_artifact_id=? LIMIT 1", (aid,)).fetchone()
            cid = change_row[0] if change_row else f"temp-chg-{aid[:10]}"
            if not change_row:
                ledger.record_change_event(cid, aid, "interface")

            cand_set = retriever.rank_candidates(cid, top_k=5)
            cands_out = []
            for cand in cand_set["candidates"]:
                verif = verifier.verify_candidate(cand["candidate_id"])
                patch_info = None
                if verif["status"] == "STALE":
                    patch = patcher.propose_patch(verif["verification_id"])
                    if patch:
                        patch_info = {
                            "patch_id": patch["patch_id"],
                            "diff": patch["diff"]
                        }
                cands_out.append({
                    "candidate_id": cand["candidate_id"],
                    "target_uri": verif.get("canonical_uri", cand["target_artifact_id"]),
                    "status": verif["status"],
                    "confidence": verif["confidence"],
                    "spans": verif.get("spans", []),
                    "patch": patch_info
                })
            inspections.append({"file": f, "candidates": cands_out})

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"inspections": inspections}).encode("utf-8"))

    def handle_api_apply(self, payload: Dict[str, Any]):
        patch_id = payload.get("patch_id")
        if not patch_id:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error": "Missing patch_id"}')
            return

        ledger = Ledger(str(self.db_path))
        patcher = PatchProposer(ledger, repo_root_override=self.repo_root)

        try:
            receipt = patcher.apply_patch(patch_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "receipt_id": receipt["receipt_id"],
                "target_file": receipt["target_file"],
                "after_hash": receipt["after_hash"]
            }).encode("utf-8"))
        except HashConflictError as e:
            self.send_response(409)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": f"CAS_HASH_CONFLICT: {str(e)}"}).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_api_reject(self, payload: Dict[str, Any]):
        patch_id = payload.get("patch_id")
        if patch_id:
            ledger = Ledger(str(self.db_path))
            with ledger.conn:
                ledger.conn.execute(
                    "UPDATE patch_proposal SET status='rejected' WHERE patch_id=?",
                    (patch_id,)
                )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"success": True, "patch_id": patch_id}).encode("utf-8"))

def start_review_server(
    repo_root: Path,
    db_path: Path,
    port: int = 8484,
    open_browser: bool = True
):
    """Starts the review server on specified port."""
    import webbrowser

    handler = lambda *args, **kwargs: DaugReviewHandler(*args, repo_root=repo_root, db_path=db_path, **kwargs)
    httpd = HTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"

    print("=" * 65)
    print(f"DAUG Interactive Review Server running at: {url}")
    print(f"Repository Root: {repo_root}")
    print(f"Database:        {db_path}")
    print("Press Ctrl+C to stop.")
    print("=" * 65)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping review server.")
    finally:
        httpd.server_close()
