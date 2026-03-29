# ChangelogHQ

Auto-generate beautiful changelogs from GitHub PRs using LLM rewriting.

## Quick Start

```bash
# Docker
docker compose up -d

# Or local
pip install -r requirements.txt
python server.py
```

## API

- `POST /projects` - Create project (name, github_repo, webhook_secret)
- `GET /projects/{id}/changelog?format=html|json|markdown` - Rendered changelog
- `POST /projects/{id}/generate` - Generate from recent PRs
- `POST /webhooks/github` - GitHub webhook (auto-generate on PR merge)
- `GET /projects/{id}/widget.js` - Embeddable widget
- `GET /projects/{id}/feed.xml` - Atom RSS feed

## MCP Server

```bash
python mcp_server.py
```

Tools: `generate_changelog`, `rewrite_changelog_entry`, `list_recent_prs`

## Widget Embed

```html
<script src="http://localhost:8440/projects/{id}/widget.js"></script>
```
