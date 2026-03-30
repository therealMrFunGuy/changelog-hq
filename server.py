"""ChangelogHQ - FastAPI REST API server."""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

import models
import github as gh
import rewriter
import renderer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("changelog-hq")

app = FastAPI(
    title="ChangelogHQ",
    description="Auto-generate beautiful changelogs from GitHub PRs using LLM rewriting.",
    version="1.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    models.init_db()
    logger.info("ChangelogHQ started")


# ── Landing Page ─────────────────────────────────────────────────────────────

LANDING_PAGE_HTML = """\
<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>ChangelogHQ — Beautiful Changelogs from GitHub PRs</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            brand: { 50:'#faf5ff',100:'#f3e8ff',200:'#e9d5ff',300:'#d8b4fe',400:'#c084fc',500:'#a855f7',600:'#9333ea',700:'#7e22ce',800:'#6b21a8',900:'#581c87' }
          }
        }
      }
    }
  </script>
  <style>
    .code-block { background: #1e1b2e; }
    .code-block code { color: #e2d9f3; font-size: 0.85rem; }
    .card-hover { transition: transform 0.15s, box-shadow 0.15s; }
    .card-hover:hover { transform: translateY(-2px); box-shadow: 0 8px 30px rgba(88,28,135,0.15); }
  </style>
</head>
<body class="bg-white text-gray-900 font-sans antialiased">

  <!-- Nav -->
  <nav class="sticky top-0 z-50 bg-white/80 backdrop-blur border-b border-gray-100">
    <div class="max-w-6xl mx-auto flex items-center justify-between px-6 py-4">
      <a href="#" class="text-xl font-bold text-brand-700 tracking-tight">ChangelogHQ</a>
      <div class="hidden md:flex items-center gap-8 text-sm font-medium text-gray-600">
        <a href="#features" class="hover:text-brand-600 transition">Features</a>
        <a href="#pricing" class="hover:text-brand-600 transition">Pricing</a>
        <a href="#api" class="hover:text-brand-600 transition">Docs</a>
        <a href="https://github.com/therealMrFunGuy/changelog-hq" target="_blank" class="hover:text-brand-600 transition">GitHub</a>
      </div>
      <a href="#api" class="hidden md:inline-block px-4 py-2 rounded-lg bg-brand-600 text-white text-sm font-semibold hover:bg-brand-700 transition">Get Started</a>
      <!-- mobile toggle -->
      <button onclick="document.getElementById('mobile-menu').classList.toggle('hidden')" class="md:hidden p-2 text-gray-500">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
      </button>
    </div>
    <div id="mobile-menu" class="hidden md:hidden px-6 pb-4 space-y-2 text-sm font-medium text-gray-600">
      <a href="#features" class="block hover:text-brand-600">Features</a>
      <a href="#pricing" class="block hover:text-brand-600">Pricing</a>
      <a href="#api" class="block hover:text-brand-600">Docs</a>
      <a href="https://github.com/therealMrFunGuy/changelog-hq" class="block hover:text-brand-600">GitHub</a>
    </div>
  </nav>

  <!-- Hero -->
  <section class="relative overflow-hidden">
    <div class="absolute inset-0 bg-gradient-to-br from-brand-50 via-white to-violet-50 -z-10"></div>
    <div class="max-w-4xl mx-auto px-6 py-24 md:py-36 text-center">
      <span class="inline-block px-3 py-1 text-xs font-semibold rounded-full bg-brand-100 text-brand-700 mb-6">v1.0 &mdash; Now Available</span>
      <h1 class="text-4xl md:text-6xl font-extrabold leading-tight tracking-tight bg-gradient-to-r from-brand-700 via-violet-600 to-brand-500 bg-clip-text text-transparent">
        Beautiful Changelogs from GitHub PRs &mdash; Automatically
      </h1>
      <p class="mt-6 text-lg md:text-xl text-gray-500 max-w-2xl mx-auto leading-relaxed">
        ChangelogHQ watches your merged PRs, rewrites them into clear, user-facing release notes with an LLM, and serves them as embeddable widgets, RSS feeds, and HTML pages.
      </p>
      <div class="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
        <a href="#api" class="px-8 py-3 rounded-xl bg-brand-600 text-white font-semibold hover:bg-brand-700 shadow-lg shadow-brand-200 transition">View API Docs</a>
        <a href="https://github.com/therealMrFunGuy/changelog-hq" target="_blank" class="px-8 py-3 rounded-xl border border-gray-300 font-semibold hover:border-brand-400 hover:text-brand-700 transition">Star on GitHub</a>
      </div>
    </div>
  </section>

  <!-- Code Examples -->
  <section class="py-20 bg-gray-50" id="demo">
    <div class="max-w-5xl mx-auto px-6">
      <h2 class="text-3xl font-bold text-center mb-4">Up and Running in Minutes</h2>
      <p class="text-center text-gray-500 mb-12 max-w-xl mx-auto">Three API calls. That's all it takes to go from zero to a live changelog.</p>

      <div class="grid md:grid-cols-2 gap-6">
        <!-- Create project -->
        <div class="code-block rounded-xl p-5 overflow-x-auto">
          <p class="text-xs text-brand-300 font-semibold uppercase tracking-wide mb-3">1 &mdash; Create a project</p>
          <code><pre class="whitespace-pre-wrap">curl -X POST http://localhost:8440/projects \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "My App",
    "github_repo": "owner/repo",
    "github_token": "ghp_..."
  }'</pre></code>
        </div>

        <!-- Generate -->
        <div class="code-block rounded-xl p-5 overflow-x-auto">
          <p class="text-xs text-brand-300 font-semibold uppercase tracking-wide mb-3">2 &mdash; Generate changelog</p>
          <code><pre class="whitespace-pre-wrap">curl -X POST \\
  http://localhost:8440/projects/{id}/generate \\
  -H "Content-Type: application/json" \\
  -d '{
    "use_llm": true,
    "max_prs": 50
  }'</pre></code>
        </div>

        <!-- Get changelog -->
        <div class="code-block rounded-xl p-5 overflow-x-auto">
          <p class="text-xs text-brand-300 font-semibold uppercase tracking-wide mb-3">3 &mdash; Fetch the result</p>
          <code><pre class="whitespace-pre-wrap"># HTML page
curl http://localhost:8440/projects/{id}/changelog?format=html

# Markdown
curl http://localhost:8440/projects/{id}/changelog?format=markdown

# JSON
curl http://localhost:8440/projects/{id}/changelog</pre></code>
        </div>

        <!-- MCP Config -->
        <div class="code-block rounded-xl p-5 overflow-x-auto">
          <p class="text-xs text-brand-300 font-semibold uppercase tracking-wide mb-3">MCP Server Config</p>
          <code><pre class="whitespace-pre-wrap">{
  "mcpServers": {
    "changelog-hq": {
      "command": "uvx",
      "args": [
        "mcp-server-changelog",
        "--base-url",
        "http://localhost:8440"
      ]
    }
  }
}</pre></code>
        </div>
      </div>
    </div>
  </section>

  <!-- Features -->
  <section class="py-20" id="features">
    <div class="max-w-5xl mx-auto px-6">
      <h2 class="text-3xl font-bold text-center mb-4">Everything You Need</h2>
      <p class="text-center text-gray-500 mb-14 max-w-lg mx-auto">From PR merge to polished release note, fully automated.</p>

      <div class="grid sm:grid-cols-2 gap-8">
        <!-- LLM Rewriting -->
        <div class="card-hover rounded-2xl border border-gray-100 p-8 bg-white">
          <div class="w-12 h-12 rounded-xl bg-brand-100 flex items-center justify-center mb-5">
            <svg class="w-6 h-6 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.3 24.3 0 0 1 4.5 0m0 0v5.714a2.25 2.25 0 0 0 .659 1.591L19 14.5m-4.25-11.396c.251.023.501.05.75.082M12 21a8.966 8.966 0 0 0 5.982-2.275M12 21a8.966 8.966 0 0 1-5.982-2.275"/></svg>
          </div>
          <h3 class="text-lg font-bold mb-2">LLM Rewriting</h3>
          <p class="text-gray-500 text-sm leading-relaxed">Transforms cryptic PR titles into clear, user-friendly release notes. Supports Claude, GPT, or any OpenAI-compatible endpoint.</p>
        </div>

        <!-- GitHub Webhooks -->
        <div class="card-hover rounded-2xl border border-gray-100 p-8 bg-white">
          <div class="w-12 h-12 rounded-xl bg-violet-100 flex items-center justify-center mb-5">
            <svg class="w-6 h-6 text-violet-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m9.86-2.04a4.5 4.5 0 0 0-1.242-7.244l-4.5-4.5a4.5 4.5 0 0 0-6.364 6.364L5.25 8.25"/></svg>
          </div>
          <h3 class="text-lg font-bold mb-2">GitHub Webhooks</h3>
          <p class="text-gray-500 text-sm leading-relaxed">Point your repo's webhook at ChangelogHQ and every merged PR automatically becomes a changelog entry. HMAC signature verification included.</p>
        </div>

        <!-- Embeddable Widget -->
        <div class="card-hover rounded-2xl border border-gray-100 p-8 bg-white">
          <div class="w-12 h-12 rounded-xl bg-purple-100 flex items-center justify-center mb-5">
            <svg class="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.25 6.75 22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3-4.5 16.5"/></svg>
          </div>
          <h3 class="text-lg font-bold mb-2">Embeddable Widget</h3>
          <p class="text-gray-500 text-sm leading-relaxed">Drop a single &lt;script&gt; tag into your site to show a "What's New" popup. Dark mode, theming, and customization built in.</p>
        </div>

        <!-- RSS Feed -->
        <div class="card-hover rounded-2xl border border-gray-100 p-8 bg-white">
          <div class="w-12 h-12 rounded-xl bg-fuchsia-100 flex items-center justify-center mb-5">
            <svg class="w-6 h-6 text-fuchsia-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12.75 19.5v-.75a7.5 7.5 0 0 0-7.5-7.5H4.5m8.25 7.5v-.75a15 15 0 0 0-15-15H4.5m0 0v.75A22.5 22.5 0 0 0 4.5 19.5m0 0h.008v.008H4.5V19.5Z"/></svg>
          </div>
          <h3 class="text-lg font-bold mb-2">RSS / Atom Feed</h3>
          <p class="text-gray-500 text-sm leading-relaxed">Every project gets an Atom feed out of the box. Let users subscribe to your changelog in their favorite reader.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- Pricing -->
  <section class="py-20 bg-gray-50" id="pricing">
    <div class="max-w-5xl mx-auto px-6">
      <h2 class="text-3xl font-bold text-center mb-4">Simple, Predictable Pricing</h2>
      <p class="text-center text-gray-500 mb-14 max-w-lg mx-auto">Start free. Upgrade when you need more.</p>

      <div class="grid md:grid-cols-3 gap-8">
        <!-- Free -->
        <div class="card-hover rounded-2xl border border-gray-200 bg-white p-8 flex flex-col">
          <h3 class="text-lg font-bold mb-1">Free</h3>
          <p class="text-4xl font-extrabold mb-1">$0</p>
          <p class="text-sm text-gray-400 mb-6">forever</p>
          <ul class="space-y-3 text-sm text-gray-600 mb-8 flex-1">
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> 3 projects</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> 100 entries / month</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> HTML, Markdown, JSON output</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Community support</li>
          </ul>
          <a href="#api" class="block text-center px-6 py-2.5 rounded-lg border border-gray-300 font-semibold text-sm hover:border-brand-400 hover:text-brand-700 transition">Get Started</a>
        </div>

        <!-- Pro -->
        <div class="card-hover rounded-2xl border-2 border-brand-500 bg-white p-8 flex flex-col relative">
          <span class="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-brand-600 text-white text-xs font-bold rounded-full">Popular</span>
          <h3 class="text-lg font-bold mb-1">Pro</h3>
          <p class="text-4xl font-extrabold mb-1">$15<span class="text-lg font-medium text-gray-400">/mo</span></p>
          <p class="text-sm text-gray-400 mb-6">per team</p>
          <ul class="space-y-3 text-sm text-gray-600 mb-8 flex-1">
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Unlimited projects</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Unlimited entries</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Custom branding</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Widget customization</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Priority support</li>
          </ul>
          <a href="#api" class="block text-center px-6 py-2.5 rounded-lg bg-brand-600 text-white font-semibold text-sm hover:bg-brand-700 shadow-lg shadow-brand-200 transition">Upgrade to Pro</a>
        </div>

        <!-- Enterprise -->
        <div class="card-hover rounded-2xl border border-gray-200 bg-white p-8 flex flex-col">
          <h3 class="text-lg font-bold mb-1">Enterprise</h3>
          <p class="text-4xl font-extrabold mb-1">Custom</p>
          <p class="text-sm text-gray-400 mb-6">contact us</p>
          <ul class="space-y-3 text-sm text-gray-600 mb-8 flex-1">
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Self-hosted LLM</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> SLA &amp; uptime guarantees</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Custom integrations</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> SSO / SAML</li>
            <li class="flex items-start gap-2"><span class="text-brand-500 mt-0.5">&#10003;</span> Dedicated support</li>
          </ul>
          <a href="mailto:hello@rjctdlabs.xyz" class="block text-center px-6 py-2.5 rounded-lg border border-gray-300 font-semibold text-sm hover:border-brand-400 hover:text-brand-700 transition">Contact Sales</a>
        </div>
      </div>
    </div>
  </section>

  <!-- API Reference -->
  <section class="py-20" id="api">
    <div class="max-w-5xl mx-auto px-6">
      <h2 class="text-3xl font-bold text-center mb-4">API Reference</h2>
      <p class="text-center text-gray-500 mb-14 max-w-lg mx-auto">RESTful JSON API. No SDK required.</p>

      <div class="space-y-6">
        <!-- POST /projects -->
        <div class="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div class="flex items-center gap-3 px-6 py-4 bg-gray-50 border-b border-gray-100">
            <span class="px-2.5 py-0.5 rounded text-xs font-bold bg-green-100 text-green-700">POST</span>
            <code class="text-sm font-mono font-semibold">/projects</code>
          </div>
          <div class="px-6 py-4 text-sm text-gray-600 space-y-2">
            <p>Create a new project to track. Returns the project object.</p>
            <p class="font-medium text-gray-700">Body parameters:</p>
            <ul class="list-disc list-inside text-gray-500 space-y-1">
              <li><code class="text-xs bg-gray-100 px-1 rounded">name</code> (string, required) &mdash; Display name</li>
              <li><code class="text-xs bg-gray-100 px-1 rounded">github_repo</code> (string, required) &mdash; e.g. "owner/repo"</li>
              <li><code class="text-xs bg-gray-100 px-1 rounded">webhook_secret</code> (string, optional) &mdash; HMAC secret for webhook verification</li>
              <li><code class="text-xs bg-gray-100 px-1 rounded">github_token</code> (string, optional) &mdash; GitHub PAT for private repos</li>
            </ul>
          </div>
        </div>

        <!-- POST /projects/{id}/generate -->
        <div class="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div class="flex items-center gap-3 px-6 py-4 bg-gray-50 border-b border-gray-100">
            <span class="px-2.5 py-0.5 rounded text-xs font-bold bg-green-100 text-green-700">POST</span>
            <code class="text-sm font-mono font-semibold">/projects/{id}/generate</code>
          </div>
          <div class="px-6 py-4 text-sm text-gray-600 space-y-2">
            <p>Trigger changelog generation from recently merged PRs. Fetches PRs from GitHub, optionally rewrites with LLM, and stores entries.</p>
            <p class="font-medium text-gray-700">Body parameters:</p>
            <ul class="list-disc list-inside text-gray-500 space-y-1">
              <li><code class="text-xs bg-gray-100 px-1 rounded">since</code> (ISO date, optional) &mdash; Only fetch PRs merged after this date</li>
              <li><code class="text-xs bg-gray-100 px-1 rounded">use_llm</code> (bool, default true) &mdash; Rewrite entries with LLM</li>
              <li><code class="text-xs bg-gray-100 px-1 rounded">max_prs</code> (int, default 50) &mdash; Max PRs to process</li>
            </ul>
          </div>
        </div>

        <!-- GET /projects/{id}/changelog -->
        <div class="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div class="flex items-center gap-3 px-6 py-4 bg-gray-50 border-b border-gray-100">
            <span class="px-2.5 py-0.5 rounded text-xs font-bold bg-blue-100 text-blue-700">GET</span>
            <code class="text-sm font-mono font-semibold">/projects/{id}/changelog</code>
          </div>
          <div class="px-6 py-4 text-sm text-gray-600 space-y-2">
            <p>Retrieve the rendered changelog in your preferred format.</p>
            <p class="font-medium text-gray-700">Query parameters:</p>
            <ul class="list-disc list-inside text-gray-500 space-y-1">
              <li><code class="text-xs bg-gray-100 px-1 rounded">format</code> &mdash; <code>json</code> (default), <code>html</code>, or <code>markdown</code></li>
              <li><code class="text-xs bg-gray-100 px-1 rounded">theme</code> &mdash; <code>auto</code>, <code>light</code>, or <code>dark</code> (HTML only)</li>
              <li><code class="text-xs bg-gray-100 px-1 rounded">limit</code> &mdash; Max entries (1-500, default 100)</li>
            </ul>
          </div>
        </div>

        <!-- GET widget -->
        <div class="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div class="flex items-center gap-3 px-6 py-4 bg-gray-50 border-b border-gray-100">
            <span class="px-2.5 py-0.5 rounded text-xs font-bold bg-blue-100 text-blue-700">GET</span>
            <code class="text-sm font-mono font-semibold">/projects/{id}/widget.js</code>
          </div>
          <div class="px-6 py-4 text-sm text-gray-600">
            <p>Embeddable JavaScript widget. Add <code class="text-xs bg-gray-100 px-1 rounded">&lt;script src="...widget.js"&gt;&lt;/script&gt;</code> to your page.</p>
          </div>
        </div>

        <!-- GET feed -->
        <div class="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div class="flex items-center gap-3 px-6 py-4 bg-gray-50 border-b border-gray-100">
            <span class="px-2.5 py-0.5 rounded text-xs font-bold bg-blue-100 text-blue-700">GET</span>
            <code class="text-sm font-mono font-semibold">/projects/{id}/feed.xml</code>
          </div>
          <div class="px-6 py-4 text-sm text-gray-600">
            <p>Atom/RSS feed for the project changelog. Subscribe in any feed reader.</p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- Footer -->
  <footer class="border-t border-gray-100 bg-gray-50">
    <div class="max-w-5xl mx-auto px-6 py-10 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-gray-400">
      <p>Powered by <a href="https://rjctdlabs.xyz" target="_blank" class="text-brand-600 hover:underline">rjctdlabs.xyz</a></p>
      <div class="flex items-center gap-6">
        <a href="https://github.com/therealMrFunGuy/changelog-hq" target="_blank" class="hover:text-brand-600 transition">GitHub</a>
        <a href="https://pypi.org/project/mcp-server-changelog/" target="_blank" class="hover:text-brand-600 transition">PyPI</a>
        <a href="/docs" class="hover:text-brand-600 transition">API Docs</a>
        <a href="/health" class="hover:text-brand-600 transition">Status</a>
      </div>
    </div>
  </footer>

</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def landing_page():
    """Serve the ChangelogHQ landing page."""
    return HTMLResponse(content=LANDING_PAGE_HTML)


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str
    github_repo: str
    webhook_secret: Optional[str] = None
    github_token: Optional[str] = None


class GenerateRequest(BaseModel):
    since: Optional[str] = None
    use_llm: bool = True
    max_prs: int = 50


# ── Project Endpoints ────────────────────────────────────────────────────────

@app.post("/projects")
async def create_project(req: CreateProjectRequest):
    """Create a new project to track."""
    project = models.create_project(
        name=req.name,
        repo=req.github_repo,
        webhook_secret=req.webhook_secret,
        github_token=req.github_token,
    )
    return {"ok": True, "project": _sanitize_project(project)}


@app.get("/projects")
async def list_projects():
    """List all projects."""
    projects = models.list_projects()
    return {"projects": [_sanitize_project(p) for p in projects]}


@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get a project by ID."""
    project = models.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": _sanitize_project(project)}


@app.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and its entries."""
    if not models.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


# ── Changelog Endpoints ─────────────────────────────────────────────────────

@app.get("/projects/{project_id}/changelog")
async def get_changelog(
    project_id: str,
    format: str = Query("json", description="Output format: json, html, markdown"),
    theme: str = Query("auto", description="Theme for HTML: auto, light, dark"),
    limit: int = Query(100, ge=1, le=500),
):
    """Get the rendered changelog for a project."""
    project = models.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    grouped = models.get_entries_grouped(project_id, limit)
    entries = models.get_entries(project_id, limit)

    if format == "html":
        html = renderer.render_changelog_html(project, grouped, theme=theme)
        return HTMLResponse(content=html)
    elif format == "markdown":
        md = renderer.render_changelog_markdown(project, grouped)
        return Response(content=md, media_type="text/markdown")
    else:
        return {
            "project": _sanitize_project(project),
            "entries": entries,
            "grouped": {k: v for k, v in grouped.items()},
            "total": len(entries),
        }


@app.post("/projects/{project_id}/generate")
async def generate_changelog(project_id: str, req: GenerateRequest):
    """Manually trigger changelog generation from recent merged PRs."""
    project = models.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    since = req.since
    if not since:
        latest = models.get_latest_entry_date(project_id)
        since = latest or (datetime.now(timezone.utc).replace(day=1)).isoformat()

    logger.info(f"Generating changelog for {project['repo']} since {since}")

    try:
        prs = await gh.fetch_merged_prs(
            repo=project["repo"],
            since=since,
            token=project.get("github_token"),
            max_prs=req.max_prs,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {e}")

    if not prs:
        return {"ok": True, "message": "No new merged PRs found", "entries_created": 0}

    # Rewrite with LLM
    if req.use_llm:
        rewritten = await rewriter.rewrite_batch(prs)
        rewrite_map = {r["number"]: r for r in rewritten}
    else:
        rewrite_map = {}

    created = []
    for pr in prs:
        rw = rewrite_map.get(pr["number"])
        title = rw["title"] if rw else pr["title"]
        body = rw["body"] if rw else ""

        entry = models.add_entry(
            project_id=project_id,
            category=pr["category"],
            title=title,
            body=body,
            pr_number=pr["number"],
            pr_url=pr["url"],
            author=pr["author"],
        )
        created.append(entry)

    models.update_project_last_generated(project_id)
    logger.info(f"Created {len(created)} changelog entries for {project['repo']}")

    return {"ok": True, "entries_created": len(created), "entries": created}


# ── GitHub Webhook ───────────────────────────────────────────────────────────

@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """Handle GitHub webhook events (PR merge triggers changelog entry)."""
    body = await request.body()
    payload = await request.json()

    event = x_github_event or ""

    if event != "pull_request":
        return {"ok": True, "message": f"Ignored event: {event}"}

    action = payload.get("action", "")
    pr = payload.get("pull_request", {})

    if action != "closed" or not pr.get("merged"):
        return {"ok": True, "message": "PR not merged, skipped"}

    repo_full_name = payload.get("repository", {}).get("full_name", "")

    # Find matching project
    projects = models.list_projects()
    project = None
    for p in projects:
        if p["repo"] == repo_full_name:
            project = p
            break

    if not project:
        return {"ok": True, "message": f"No project found for repo {repo_full_name}"}

    # Validate webhook signature if secret is set
    if project.get("webhook_secret"):
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing signature")
        expected = "sha256=" + hmac.new(
            project["webhook_secret"].encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Process the merged PR
    labels = [l["name"] for l in pr.get("labels", [])]
    category = gh.classify_pr(labels, pr["title"])

    # Try LLM rewrite
    rw = await rewriter.rewrite_entry(pr["title"], pr.get("body") or "", category)

    entry = models.add_entry(
        project_id=project["id"],
        category=category,
        title=rw["title"],
        body=rw["body"],
        pr_number=pr["number"],
        pr_url=pr.get("html_url", ""),
        author=pr.get("user", {}).get("login", "unknown"),
    )

    logger.info(f"Webhook: created entry for PR #{pr['number']} in {repo_full_name}")
    return {"ok": True, "entry": entry}


# ── Widget & Feed ────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/widget.js")
async def get_widget(project_id: str, request: Request):
    """Get the embeddable 'What's New' widget JavaScript."""
    project = models.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    entries = models.get_entries(project_id, limit=20)
    base_url = str(request.base_url).rstrip("/")
    js = renderer.render_widget_js(project, entries, base_url)
    return Response(content=js, media_type="application/javascript")


@app.get("/projects/{project_id}/feed.xml")
async def get_feed(project_id: str, request: Request):
    """Get RSS/Atom feed for a project's changelog."""
    project = models.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    entries = models.get_entries(project_id, limit=50)
    base_url = str(request.base_url).rstrip("/")
    xml = renderer.render_rss_feed(project, entries, base_url)
    return Response(content=xml, media_type="application/atom+xml")


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "changelog-hq", "version": "1.0.0"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sanitize_project(p: dict) -> dict:
    """Remove sensitive fields from project data."""
    safe = dict(p)
    safe.pop("github_token", None)
    safe.pop("webhook_secret", None)
    safe["has_webhook_secret"] = bool(p.get("webhook_secret"))
    safe["has_github_token"] = bool(p.get("github_token"))
    return safe


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8440"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
