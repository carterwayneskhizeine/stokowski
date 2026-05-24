"""Optional web dashboard and API (requires fastapi + uvicorn)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .orchestrator import MultiOrchestrator

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
except ImportError:
    raise ImportError("Install web extras: pip install stokowski[web]")

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stokowski</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #080808;
    --surface:   #0f0f0f;
    --border:    #1c1c1c;
    --border-hi: #2a2a2a;
    --text:      #e8e8e0;
    --muted:     #555550;
    --dim:       #333330;
    --amber:     #e8b84b;
    --amber-dim: #6b5220;
    --green:     #4cba6e;
    --red:       #d95f52;
    --blue:      #5b9cf6;
    --font:      'IBM Plex Mono', monospace;
  }

  html, body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    line-height: 1.5;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* Subtle grid background */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(var(--border) 1px, transparent 1px),
      linear-gradient(90deg, var(--border) 1px, transparent 1px);
    background-size: 40px 40px;
    opacity: 0.35;
    pointer-events: none;
    z-index: 0;
  }

  .shell {
    position: relative;
    z-index: 1;
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 24px 60px;
  }

  /* ── Header ── */
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 28px 0 24px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
  }

  .logo {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  .logo-name {
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.5px;
    color: var(--text);
  }

  .logo-tag {
    font-size: 11px;
    font-weight: 300;
    color: var(--muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 24px;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: pulse-green 2.5s ease-in-out infinite;
  }

  .status-dot.idle {
    background: var(--muted);
    box-shadow: none;
    animation: none;
  }

  @keyframes pulse-green {
    0%, 100% { opacity: 1; box-shadow: 0 0 6px var(--green); }
    50%       { opacity: 0.5; box-shadow: 0 0 12px var(--green); }
  }

  .timestamp {
    font-size: 11px;
    color: var(--muted);
    font-weight: 300;
    letter-spacing: 0.04em;
  }

  /* ── Metrics row ── */
  .metrics {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    margin-bottom: 32px;
  }

  .metric {
    background: var(--surface);
    padding: 20px 24px;
    position: relative;
    overflow: hidden;
  }

  .metric::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 2px;
    background: var(--border-hi);
    transition: background 0.3s;
  }

  .metric.active::after {
    background: var(--amber);
  }

  .metric-label {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 8px;
  }

  .metric-value {
    font-size: 32px;
    font-weight: 600;
    color: var(--text);
    line-height: 1;
    letter-spacing: -1px;
    transition: color 0.3s;
  }

  .metric.active .metric-value {
    color: var(--amber);
  }

  .metric-sub {
    font-size: 11px;
    color: var(--muted);
    margin-top: 6px;
    font-weight: 300;
  }

  /* ── Section headers ── */
  .section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  .section-title {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .section-line {
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  .section-count {
    font-size: 10px;
    color: var(--dim);
    font-weight: 300;
  }

  /* ── Agent cards ── */
  .agents {
    display: flex;
    flex-direction: column;
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    margin-bottom: 32px;
  }

  .agent-card {
    background: var(--surface);
    padding: 18px 24px;
    display: grid;
    grid-template-columns: 100px 1fr auto;
    gap: 16px;
    align-items: start;
    transition: background 0.15s;
    cursor: pointer;
  }

  .agent-card:hover {
    background: #141414;
  }

  .agent-id {
    font-size: 13px;
    font-weight: 600;
    color: var(--amber);
    letter-spacing: 0.02em;
  }

  .agent-status-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .status-pill {
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 2px;
  }

  .status-pill.streaming {
    background: rgba(232, 184, 75, 0.12);
    color: var(--amber);
    border: 1px solid var(--amber-dim);
  }

  .status-pill.streaming::before {
    content: '▶ ';
    animation: blink 1.2s step-end infinite;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0; }
  }

  .status-pill.succeeded  { background: rgba(76,186,110,.1); color: var(--green); border: 1px solid rgba(76,186,110,.25); }
  .status-pill.failed     { background: rgba(217,95,82,.1);  color: var(--red);   border: 1px solid rgba(217,95,82,.25); }
  .status-pill.retrying   { background: rgba(91,156,246,.1); color: var(--blue);  border: 1px solid rgba(91,156,246,.25); }
  .status-pill.pending    { background: transparent;          color: var(--muted); border: 1px solid var(--border-hi); }
  .status-pill.gate { background: rgba(232, 184, 75, 0.08); color: var(--amber-dim); border: 1px solid var(--amber-dim); }

  .agent-msg {
    font-size: 12px;
    color: var(--muted);
    font-weight: 300;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 620px;
  }

  .agent-meta {
    text-align: right;
    white-space: nowrap;
  }

  .agent-tokens {
    font-size: 12px;
    color: var(--text);
    font-weight: 500;
    margin-bottom: 3px;
  }

  .agent-turns {
    font-size: 11px;
    color: var(--muted);
    font-weight: 300;
  }

  /* ── Projects tiles ── */
  .projects-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    margin-bottom: 32px;
  }

  .project-tile {
    background: var(--surface);
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: background 0.15s;
  }

  .project-tile:hover {
    background: #141414;
  }

  .project-tile.paused {
    opacity: 0.55;
  }

  .project-tile-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .project-tile-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--amber);
    letter-spacing: 0.02em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 140px;
  }

  .pause-btn {
    background: transparent;
    border: 1px solid var(--border-hi);
    color: var(--muted);
    font-family: var(--font);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 3px 8px;
    border-radius: 2px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .pause-btn:hover {
    border-color: var(--amber-dim);
    color: var(--amber);
  }

  .pause-btn.paused {
    border-color: var(--red);
    color: var(--red);
  }

  .project-tile-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    font-size: 11px;
  }

  .project-stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .project-stat-label {
    font-size: 9px;
    color: var(--muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .project-stat-value {
    color: var(--text);
    font-weight: 500;
    font-size: 13px;
  }

  /* ── Filter dropdown ── */
  .filter-select {
    background: var(--surface);
    border: 1px solid var(--border-hi);
    color: var(--text);
    font-family: var(--font);
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 2px;
    cursor: pointer;
  }

  .filter-select:focus {
    outline: none;
    border-color: var(--amber-dim);
  }

  /* ── Queue panel ── */
  .queue-card {
    background: var(--surface);
    padding: 12px 18px;
    display: grid;
    grid-template-columns: 100px 1fr auto;
    gap: 14px;
    align-items: center;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
  }

  .queue-card:last-child {
    border-bottom: none;
  }

  .queue-id {
    color: var(--amber);
    font-weight: 600;
    font-size: 12px;
  }

  .queue-title {
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 600px;
  }

  .queue-reason {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 2px 8px;
    border: 1px solid var(--border-hi);
    border-radius: 2px;
  }

  .queue-reason.paused {
    color: var(--red);
    border-color: var(--red);
  }

  .agent-project {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.05em;
    margin-top: 2px;
  }

  /* ── Empty state ── */
  .empty {
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 48px 24px;
    text-align: center;
    margin-bottom: 32px;
  }

  .empty-title {
    font-size: 13px;
    color: var(--dim);
    margin-bottom: 6px;
    font-weight: 300;
    letter-spacing: 0.06em;
  }

  .empty-sub {
    font-size: 11px;
    color: var(--border-hi);
    font-weight: 300;
  }

  /* ── Stats bar ── */
  .stats-bar {
    display: flex;
    align-items: center;
    gap: 24px;
    padding: 14px 0;
    border-top: 1px solid var(--border);
    margin-top: 8px;
  }

  .stat-item {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .stat-label {
    font-size: 10px;
    color: var(--muted);
    font-weight: 300;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .stat-value {
    font-size: 12px;
    color: var(--text);
    font-weight: 500;
  }

  .stat-divider {
    width: 1px;
    height: 16px;
    background: var(--border);
  }

  /* ── Progress bar ── */
  .progress-wrap {
    flex: 1;
    height: 2px;
    background: var(--border);
    overflow: hidden;
    border-radius: 1px;
  }

  .progress-bar {
    height: 100%;
    background: var(--amber);
    animation: scan 3s linear infinite;
    transform-origin: left;
  }

  @keyframes scan {
    0%   { transform: scaleX(0) translateX(0); }
    50%  { transform: scaleX(1) translateX(0); }
    100% { transform: scaleX(0) translateX(100%); }
  }

  /* ── Footer ── */
  footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 0 0;
    border-top: 1px solid var(--border);
    margin-top: 32px;
  }

  .footer-left {
    font-size: 11px;
    color: var(--dim);
    font-weight: 300;
  }

  .footer-right {
    font-size: 11px;
    color: var(--dim);
    font-weight: 300;
  }

  /* ── Comment drawer ── */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.65);
    z-index: 200;
    display: flex;
    justify-content: flex-end;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.18s;
  }

  .modal-overlay.open {
    opacity: 1;
    pointer-events: all;
  }

  .modal-drawer {
    background: #0d0d0d;
    border-left: 1px solid var(--border-hi);
    width: 560px;
    max-width: 92vw;
    height: 100vh;
    display: flex;
    flex-direction: column;
    transform: translateX(100%);
    transition: transform 0.18s;
    overflow: hidden;
  }

  .modal-overlay.open .modal-drawer {
    transform: translateX(0);
  }

  .modal-header {
    padding: 20px 24px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    gap: 12px;
  }

  .modal-header-left {
    display: flex;
    align-items: baseline;
    gap: 10px;
    overflow: hidden;
    min-width: 0;
  }

  .modal-issue-id {
    font-size: 14px;
    font-weight: 600;
    color: var(--amber);
    flex-shrink: 0;
  }

  .modal-issue-title {
    font-size: 12px;
    color: var(--muted);
    font-weight: 300;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .modal-close {
    background: transparent;
    border: 1px solid var(--border-hi);
    color: var(--muted);
    font-family: var(--font);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 4px 10px;
    border-radius: 2px;
    cursor: pointer;
    flex-shrink: 0;
    transition: all 0.15s;
  }

  .modal-close:hover {
    border-color: var(--amber-dim);
    color: var(--amber);
  }

  .modal-body {
    flex: 1;
    overflow-y: auto;
    padding: 20px 24px;
  }

  .comment-list {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .comment-item {
    padding: 14px 0 14px 16px;
    border-left: 2px solid var(--border);
    position: relative;
  }

  .comment-item + .comment-item {
    border-top: none;
    margin-top: 0;
  }

  .comment-item.tracking {
    border-left-color: var(--amber-dim);
  }

  .comment-item::before {
    content: '';
    position: absolute;
    left: -5px;
    top: 20px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--border-hi);
    border: 1px solid var(--border);
  }

  .comment-item.tracking::before {
    background: var(--amber-dim);
    border-color: var(--amber-dim);
  }

  .comment-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .comment-badge {
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 1px 6px;
    border-radius: 2px;
    background: rgba(232, 184, 75, 0.08);
    color: var(--amber);
    border: 1px solid var(--amber-dim);
  }

  .comment-time {
    font-size: 10px;
    color: var(--muted);
    font-weight: 300;
    letter-spacing: 0.03em;
  }

  .comment-text {
    font-size: 12px;
    color: var(--text);
    font-weight: 300;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.65;
  }

  .comment-text.muted {
    color: var(--muted);
  }

  .comment-placeholder {
    text-align: center;
    padding: 48px 0;
    color: var(--muted);
    font-size: 12px;
    font-weight: 300;
    letter-spacing: 0.04em;
  }

  /* ── Drawer section headers ── */
  .drawer-section-header {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    padding: 20px 0 8px;
    border-bottom: 1px solid var(--border);
  }
  .drawer-section-header:first-child { padding-top: 4px; }

  /* ── Thinking log items ── */
  .think-item {
    position: relative;
    padding: 10px 0 10px 16px;
    border-left: 2px solid #222;
  }
  .think-item + .think-item { margin-top: 2px; }
  .think-item::before {
    content: '';
    position: absolute;
    left: -5px; top: 14px;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #333;
    border: 2px solid var(--bg);
  }
  .think-item.tool  { border-left-color: #1a3828; }
  .think-item.tool::before  { background: #2d7a50; }
  .think-item.result { border-left-color: var(--amber-dim); }
  .think-item.result::before { background: var(--amber-dim); }

  .think-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  .think-badge {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 2px;
    background: #1a1a1a;
    color: var(--muted);
  }
  .think-badge.tool   { background: #162318; color: #4caf50; }
  .think-badge.result { background: #251c00; color: var(--amber); }
  .think-time { font-size: 10px; color: var(--muted); }

  .think-text {
    font-size: 12px;
    line-height: 1.6;
    color: #999;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .think-tool-name {
    font-size: 12px;
    color: #4caf50;
    font-weight: 600;
    margin-bottom: 4px;
  }
  .think-input {
    font-size: 11px;
    color: #777;
    background: #0d0d0d;
    border: 1px solid #1c1c1c;
    border-radius: 3px;
    padding: 6px 8px;
    white-space: pre-wrap;
    word-break: break-word;
    margin-top: 4px;
  }
</style>
</head>
<body>
<div class="shell">

  <header>
    <div class="logo">
      <span class="logo-name">STOKOWSKI</span>
      <span class="logo-tag">Claude Code Orchestrator</span>
    </div>
    <div class="header-right">
      <div id="status-dot" class="status-dot idle"></div>
      <span id="ts" class="timestamp">—</span>
    </div>
  </header>

  <div class="metrics">
    <div class="metric" id="m-running">
      <div class="metric-label">Running</div>
      <div class="metric-value" id="v-running">—</div>
      <div class="metric-sub">active agents</div>
    </div>
    <div class="metric" id="m-retrying">
      <div class="metric-label">Queued</div>
      <div class="metric-value" id="v-retrying">—</div>
      <div class="metric-sub">retry / waiting</div>
    </div>
    <div class="metric" id="m-tokens">
      <div class="metric-label">Tokens</div>
      <div class="metric-value" id="v-tokens">—</div>
      <div class="metric-sub" id="v-tokens-sub">total consumed</div>
    </div>
    <div class="metric" id="m-runtime">
      <div class="metric-label">Runtime</div>
      <div class="metric-value" id="v-runtime">—</div>
      <div class="metric-sub">cumulative seconds</div>
    </div>
  </div>

  <div id="projects-section" style="display:none">
    <div class="section-header">
      <span class="section-title">Projects</span>
      <div class="section-line"></div>
      <span class="section-count" id="project-count">0</span>
    </div>
    <div id="projects-grid" class="projects-grid"></div>
  </div>

  <div class="section-header">
    <span class="section-title">Active Agents</span>
    <div class="section-line"></div>
    <select id="project-filter" class="filter-select" onchange="window.__stokowskiSetFilter(this.value)">
      <option value="">All projects</option>
    </select>
    <span class="section-count" id="agent-count">0</span>
  </div>

  <div id="agents-container"></div>

  <div id="queue-section" style="display:none">
    <div class="section-header">
      <span class="section-title">Queued (eligible, waiting)</span>
      <div class="section-line"></div>
      <span class="section-count" id="queue-count">0</span>
    </div>
    <div id="queue-container"></div>
  </div>

  <div class="stats-bar">
    <div class="stat-item">
      <span class="stat-label">In</span>
      <span class="stat-value" id="s-in">—</span>
    </div>
    <div class="stat-divider"></div>
    <div class="stat-item">
      <span class="stat-label">Out</span>
      <span class="stat-value" id="s-out">—</span>
    </div>
    <div class="stat-divider"></div>
    <div id="progress-container" style="display:none; flex:1; align-items:center; gap:12px;">
      <span class="stat-label">Working</span>
      <div class="progress-wrap"><div class="progress-bar"></div></div>
    </div>
  </div>

  <footer>
    <span class="footer-left">Refreshes every 3s — click any issue to view comment history</span>
    <span class="footer-right" id="footer-gen">—</span>
  </footer>

</div>

<div id="modal-overlay" class="modal-overlay">
  <div class="modal-drawer" id="modal-drawer">
    <div class="modal-header">
      <div class="modal-header-left">
        <span id="modal-issue-id" class="modal-issue-id"></span>
        <span id="modal-issue-title" class="modal-issue-title"></span>
      </div>
      <button class="modal-close" id="modal-close-btn">close ×</button>
    </div>
    <div class="modal-body" id="modal-body">
      <div class="comment-placeholder">Select an issue to view comments</div>
    </div>
  </div>
</div>

<script>
  function esc(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmt(n) {
    if (n >= 1000000) return (n/1000000).toFixed(1) + 'M';
    if (n >= 1000)    return (n/1000).toFixed(1) + 'K';
    return n.toString();
  }

  function fmtSecs(s) {
    if (s < 60)   return Math.round(s) + 's';
    if (s < 3600) return Math.floor(s/60) + 'm ' + Math.round(s%60) + 's';
    return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
  }

  function statusPill(status) {
    const cls = ['streaming','succeeded','failed','retrying','pending','gate'].includes(status) ? status : 'pending';
    const label = status === 'streaming' ? 'live' : status === 'gate' ? 'awaiting gate' : status;
    return `<span class="status-pill ${cls}">${label}</span>`;
  }

  // Filter state — null means "all projects". Persisted across refreshes.
  let activeFilter = '';
  window.__stokowskiSetFilter = (val) => { activeFilter = val || ''; refresh(); };

  function projectMatches(item) {
    if (!activeFilter) return true;
    return (item.project_name || '') === activeFilter;
  }

  async function togglePause(name) {
    try {
      await fetch('/api/v1/projects/' + encodeURIComponent(name) + '/toggle', { method: 'POST' });
      refresh();
    } catch (e) { /* ignore */ }
  }
  window.__stokowskiTogglePause = togglePause;

  function renderProjects(data) {
    const projects = data.projects || [];
    const section = document.getElementById('projects-section');
    if (projects.length <= 1) {
      // Hide the projects section for single-project setups — keeps the
      // dashboard clean when there's no multi-project context to surface.
      section.style.display = 'none';
    } else {
      section.style.display = '';
    }
    document.getElementById('project-count').textContent = projects.length;

    // Update filter dropdown options (preserve current selection)
    const sel = document.getElementById('project-filter');
    const current = sel.value;
    const wantedNames = projects.map(p => p.name);
    const existingOpts = Array.from(sel.options).map(o => o.value);
    const same = wantedNames.length === existingOpts.length - 1 &&
      wantedNames.every((n, i) => existingOpts[i + 1] === n);
    if (!same) {
      sel.innerHTML = '<option value="">All projects</option>' +
        wantedNames.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
      sel.value = wantedNames.includes(current) ? current : '';
      activeFilter = sel.value;
    }

    document.getElementById('projects-grid').innerHTML = projects.map(p => {
      const tokens = p.totals?.total_tokens || 0;
      const pauseLabel = p.paused ? 'Resume' : 'Pause';
      const pauseClass = p.paused ? 'pause-btn paused' : 'pause-btn';
      return `
        <div class="project-tile ${p.paused ? 'paused' : ''}">
          <div class="project-tile-head">
            <span class="project-tile-name" title="${esc(p.name)}">${esc(p.name)}</span>
            <button class="${pauseClass}" onclick="window.__stokowskiTogglePause('${esc(p.name)}')">${pauseLabel}</button>
          </div>
          <div class="project-tile-stats">
            <div class="project-stat">
              <span class="project-stat-label">Run</span>
              <span class="project-stat-value">${p.counts?.running || 0}</span>
            </div>
            <div class="project-stat">
              <span class="project-stat-label">Gates</span>
              <span class="project-stat-value">${p.counts?.gates || 0}</span>
            </div>
            <div class="project-stat">
              <span class="project-stat-label">Queue</span>
              <span class="project-stat-value">${p.counts?.queued || 0}</span>
            </div>
            <div class="project-stat">
              <span class="project-stat-label">Tokens</span>
              <span class="project-stat-value">${fmt(tokens)}</span>
            </div>
          </div>
        </div>`;
    }).join('');
  }

  function renderQueue(data) {
    const queue = (data.queued || []).filter(projectMatches);
    const section = document.getElementById('queue-section');
    if (queue.length === 0) {
      section.style.display = 'none';
      return;
    }
    section.style.display = '';
    document.getElementById('queue-count').textContent = queue.length;
    document.getElementById('queue-container').innerHTML =
      `<div class="agents">` + queue.map(q => {
        const pausedReason = (q.reason || '').toLowerCase().includes('paused');
        return `
          <div class="queue-card">
            <div>
              <div class="queue-id">${esc(q.issue_identifier)}</div>
              ${q.project_name ? `<div class="agent-project">${esc(q.project_name)}</div>` : ''}
            </div>
            <div class="queue-title">${esc(q.title || '—')}</div>
            <div class="queue-reason ${pausedReason ? 'paused' : ''}">${esc(q.reason || '')}</div>
          </div>`;
      }).join('') + `</div>`;
  }

  function renderAgents(data) {
    const all = [
      ...(data.running || []),
      ...(data.retrying || []).map(r => ({
        issue_identifier: r.issue_identifier,
        project_name: r.project_name,
        status: 'retrying',
        turn_count: r.attempt,
        tokens: { total_tokens: 0 },
        last_message: r.error || 'waiting to retry...',
        session_id: null,
      })),
      ...(data.gates || []).map(g => ({
        issue_identifier: g.issue_identifier,
        project_name: g.project_name,
        status: 'gate',
        state_name: g.gate_state,
        turn_count: g.run,
        tokens: { total_tokens: 0 },
        last_message: 'Awaiting human review',
        session_id: null,
      })),
    ].filter(projectMatches);

    document.getElementById('agent-count').textContent = all.length;

    if (all.length === 0) {
      document.getElementById('agents-container').innerHTML = `
        <div class="empty">
          <div class="empty-title">No active agents</div>
          <div class="empty-sub">Move a Linear issue to Todo or In Progress to start</div>
        </div>`;
      return;
    }

    const rows = all.map(r => {
      const stateInfo = r.state_name ? `<span style="color:var(--muted);font-size:11px;margin-left:8px">${esc(r.state_name)}</span>` : '';
      const projTag = r.project_name ? `<div class="agent-project">${esc(r.project_name)}</div>` : '';
      return `
      <div class="agent-card" onclick="window.__stokowskiOpenIssue('${esc(r.issue_identifier)}')">
        <div>
          <div class="agent-id">${esc(r.issue_identifier)}</div>
          ${projTag}
        </div>
        <div>
          <div class="agent-status-row">
            ${statusPill(r.status)}${stateInfo}
          </div>
          <div class="agent-msg">${esc(r.last_message || '—')}</div>
        </div>
        <div class="agent-meta">
          <div class="agent-tokens">${fmt(r.tokens?.total_tokens || 0)} tok</div>
          <div class="agent-turns">turn ${r.turn_count || 0}</div>
        </div>
      </div>`;
    }).join('');

    document.getElementById('agents-container').innerHTML =
      `<div class="agents">${rows}</div>`;
  }

  async function refresh() {
    try {
      const res = await fetch('/api/v1/state');
      const data = await res.json();

      const running  = data.counts?.running  || 0;
      const retrying = data.counts?.retrying || 0;
      const active   = running > 0;

      // Metrics
      document.getElementById('v-running').textContent  = running;
      const gates = data.counts?.gates || 0;
      document.getElementById('v-retrying').textContent = retrying + gates;
      document.getElementById('v-tokens').textContent   = fmt(data.totals?.total_tokens || 0);
      document.getElementById('v-runtime').textContent  = fmtSecs(data.totals?.seconds_running || 0);

      document.getElementById('m-running').className  = 'metric' + (active ? ' active' : '');
      document.getElementById('m-tokens').className   = 'metric' + (data.totals?.total_tokens > 0 ? ' active' : '');

      // Stats bar
      document.getElementById('s-in').textContent  = fmt(data.totals?.input_tokens  || 0);
      document.getElementById('s-out').textContent = fmt(data.totals?.output_tokens || 0);

      // Progress bar
      const pc = document.getElementById('progress-container');
      pc.style.display = active ? 'flex' : 'none';

      // Status dot
      const dot = document.getElementById('status-dot');
      dot.className = 'status-dot' + (active ? '' : ' idle');

      // Timestamp
      const now = new Date();
      document.getElementById('ts').textContent =
        now.toLocaleTimeString('en-US', { hour12: false }) + ' local';
      document.getElementById('footer-gen').textContent =
        'last sync ' + now.toLocaleTimeString('en-US', { hour12: false });

      renderProjects(data);
      renderAgents(data);
      renderQueue(data);
    } catch(e) {
      document.getElementById('status-dot').className = 'status-dot idle';
    }
  }

  refresh();
  setInterval(refresh, 3000);

  // ── Comment drawer ──────────────────────────────────────────────────────
  const overlay   = document.getElementById('modal-overlay');
  const drawer    = document.getElementById('modal-drawer');
  const closeBtn  = document.getElementById('modal-close-btn');

  function openDrawer(identifier) {
    document.getElementById('modal-issue-id').textContent    = identifier;
    document.getElementById('modal-issue-title').textContent = '';
    document.getElementById('modal-body').innerHTML =
      '<div class="comment-placeholder">Loading…</div>';
    overlay.classList.add('open');
    loadComments(identifier);
  }

  function closeDrawer() {
    overlay.classList.remove('open');
  }

  closeBtn.addEventListener('click', closeDrawer);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeDrawer(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
  window.__stokowskiOpenIssue = openDrawer;

  async function loadComments(identifier) {
    try {
      const res  = await fetch('/api/v1/issues/' + encodeURIComponent(identifier) + '/comments');
      const data = await res.json();
      if (!res.ok) {
        document.getElementById('modal-body').innerHTML =
          '<div class="comment-placeholder">Failed to load comments.</div>';
        return;
      }
      document.getElementById('modal-issue-title').textContent = data.issue_title || '';
      const comments    = data.comments     || [];
      const thinkingLog = data.thinking_log || [];

      if (comments.length === 0 && thinkingLog.length === 0) {
        document.getElementById('modal-body').innerHTML =
          '<div class="comment-placeholder">No activity recorded for this issue yet.</div>';
        return;
      }

      let html = '';
      if (thinkingLog.length > 0) {
        html += '<div class="drawer-section-header">AI 思考过程</div>';
        html += '<div class="comment-list">' + thinkingLog.map(renderThinkingEntry).join('') + '</div>';
      }
      if (comments.length > 0) {
        html += '<div class="drawer-section-header">Linear 评论</div>';
        html += '<div class="comment-list">' + comments.map(renderComment).join('') + '</div>';
      }
      document.getElementById('modal-body').innerHTML = html;
    } catch (e) {
      document.getElementById('modal-body').innerHTML =
        '<div class="comment-placeholder">Failed to load comments.</div>';
    }
  }

  function fmtThinkTime(ts) {
    if (!ts) return '';
    return new Date(ts).toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  }

  function renderThinkingEntry(e) {
    const time = '<span class="think-time">' + esc(fmtThinkTime(e.ts)) + '</span>';
    if (e.type === 'tool_use') {
      const inputLines = Object.entries(e.input || {}).map(([k, v]) => k + ': ' + v).join('\\n');
      return (
        '<div class="think-item tool">' +
          '<div class="think-meta"><span class="think-badge tool">tool</span>' + time + '</div>' +
          '<div class="think-tool-name">' + esc(e.name || '') + '</div>' +
          (inputLines ? '<div class="think-input">' + esc(inputLines) + '</div>' : '') +
        '</div>'
      );
    }
    if (e.type === 'result') {
      return (
        '<div class="think-item result">' +
          '<div class="think-meta"><span class="think-badge result">result</span>' + time + '</div>' +
          '<div class="think-text">' + esc(e.text || '') + '</div>' +
        '</div>'
      );
    }
    return (
      '<div class="think-item">' +
        '<div class="think-meta"><span class="think-badge">assistant</span>' + time + '</div>' +
        '<div class="think-text">' + esc(e.text || '') + '</div>' +
      '</div>'
    );
  }

  function renderComment(c) {
    const body = c.body || '';
    const isTracking = body.includes('<!-- stokowski:state') || body.includes('<!-- stokowski:gate');
    // Strip hidden HTML comments so machine JSON doesn't pollute the display
    const display = body.replace(/<!--[\\s\\S]*?-->/g, '').trim();
    const time = c.createdAt
      ? new Date(c.createdAt).toLocaleString('en-US', {
          month: 'short', day: 'numeric',
          hour: '2-digit', minute: '2-digit', hour12: false,
        })
      : '';
    const badge  = isTracking ? '<span class="comment-badge">stokowski</span>' : '';
    const cls    = isTracking ? 'tracking' : '';
    const txtCls = display ? '' : ' muted';
    const txt    = display || '(empty)';
    return (
      '<div class="comment-item ' + cls + '">' +
        '<div class="comment-meta">' + badge +
          '<span class="comment-time">' + esc(time) + '</span>' +
        '</div>' +
        '<div class="comment-text' + txtCls + '">' + esc(txt) + '</div>' +
      '</div>'
    );
  }
</script>
</body>
</html>
"""


def create_app(orchestrator: "MultiOrchestrator") -> FastAPI:
    app = FastAPI(title="Stokowski", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/api/v1/state")
    async def api_state():
        return JSONResponse(orchestrator.get_state_snapshot())

    @app.get("/api/v1/{issue_identifier}")
    async def api_issue(issue_identifier: str):
        snap = orchestrator.get_state_snapshot()
        for r in snap["running"]:
            if r["issue_identifier"] == issue_identifier:
                return JSONResponse(r)
        for r in snap["retrying"]:
            if r["issue_identifier"] == issue_identifier:
                return JSONResponse(r)
        for g in snap["gates"]:
            if g["issue_identifier"] == issue_identifier:
                return JSONResponse(g)
        return JSONResponse(
            {"error": {"code": "issue_not_found", "message": f"Unknown: {issue_identifier}"}},
            status_code=404,
        )

    @app.post("/api/v1/refresh")
    async def api_refresh():
        asyncio.create_task(orchestrator.force_tick())
        return JSONResponse({"ok": True})

    @app.get("/api/v1/issues/{issue_identifier}/comments")
    async def api_issue_comments(issue_identifier: str):
        result = await orchestrator.fetch_issue_comments(issue_identifier)
        if result is None:
            return JSONResponse(
                {"error": {"code": "issue_not_found", "message": f"Unknown: {issue_identifier}"}},
                status_code=404,
            )
        return JSONResponse(result)

    @app.post("/api/v1/projects/{project_name}/pause")
    async def api_project_pause(project_name: str):
        if not orchestrator.pause(project_name):
            return JSONResponse(
                {"error": {"code": "project_not_found", "message": project_name}},
                status_code=404,
            )
        return JSONResponse({"ok": True, "project": project_name, "paused": True})

    @app.post("/api/v1/projects/{project_name}/resume")
    async def api_project_resume(project_name: str):
        if not orchestrator.resume(project_name):
            return JSONResponse(
                {"error": {"code": "project_not_found", "message": project_name}},
                status_code=404,
            )
        return JSONResponse({"ok": True, "project": project_name, "paused": False})

    @app.post("/api/v1/projects/{project_name}/toggle")
    async def api_project_toggle(project_name: str):
        if project_name not in orchestrator.project_names:
            return JSONResponse(
                {"error": {"code": "project_not_found", "message": project_name}},
                status_code=404,
            )
        now_paused = orchestrator.toggle(project_name)
        return JSONResponse({"ok": True, "project": project_name, "paused": now_paused})

    return app
