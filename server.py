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
