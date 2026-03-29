"""ChangelogHQ MCP Server - Tools for changelog generation via MCP protocol."""

import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import github as gh
import rewriter

server = Server("changelog-hq")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="generate_changelog",
            description="Generate a formatted changelog from recent merged GitHub PRs. Takes a GitHub repo (owner/repo) and optional since_date, returns a categorized changelog with user-friendly descriptions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "github_repo": {
                        "type": "string",
                        "description": "GitHub repository in owner/repo format (e.g. 'vercel/next.js')",
                    },
                    "since_date": {
                        "type": "string",
                        "description": "ISO date to fetch PRs from (default: last 30 days). Example: '2025-01-01'",
                    },
                    "github_token": {
                        "type": "string",
                        "description": "Optional GitHub token for private repos or higher rate limits",
                    },
                    "use_llm": {
                        "type": "boolean",
                        "description": "Whether to use LLM to rewrite PR descriptions (default: true)",
                        "default": True,
                    },
                    "max_prs": {
                        "type": "integer",
                        "description": "Maximum number of PRs to include (default: 30)",
                        "default": 30,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "description": "Output format: markdown or json (default: markdown)",
                        "default": "markdown",
                    },
                },
                "required": ["github_repo"],
            },
        ),
        Tool(
            name="rewrite_changelog_entry",
            description="Rewrite technical PR text into a user-friendly changelog entry using LLM.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The technical text to rewrite (PR title, description, etc.)",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["feature", "fix", "improvement", "breaking", "docs", "chore"],
                        "description": "Category of the change",
                        "default": "improvement",
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="list_recent_prs",
            description="Fetch and summarize recent merged PRs from a GitHub repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "github_repo": {
                        "type": "string",
                        "description": "GitHub repository in owner/repo format",
                    },
                    "since_date": {
                        "type": "string",
                        "description": "ISO date to fetch PRs from (default: last 14 days)",
                    },
                    "github_token": {
                        "type": "string",
                        "description": "Optional GitHub token",
                    },
                    "max_prs": {
                        "type": "integer",
                        "description": "Maximum PRs to return (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["github_repo"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "generate_changelog":
        return await _generate_changelog(arguments)
    elif name == "rewrite_changelog_entry":
        return await _rewrite_entry(arguments)
    elif name == "list_recent_prs":
        return await _list_recent_prs(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _generate_changelog(args: dict) -> list[TextContent]:
    repo = args["github_repo"]
    since = args.get("since_date")
    token = args.get("github_token")
    use_llm = args.get("use_llm", True)
    max_prs = args.get("max_prs", 30)
    fmt = args.get("format", "markdown")

    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        prs = await gh.fetch_merged_prs(repo, since=since, token=token, max_prs=max_prs)
    except Exception as e:
        return [TextContent(type="text", text=f"Error fetching PRs from {repo}: {e}")]

    if not prs:
        return [TextContent(type="text", text=f"No merged PRs found in {repo} since {since}.")]

    # Rewrite with LLM if requested
    if use_llm:
        rewritten = await rewriter.rewrite_batch(prs)
        rewrite_map = {r["number"]: r for r in rewritten}
    else:
        rewrite_map = {}

    # Group by category
    grouped: dict[str, list] = {}
    for pr in prs:
        cat = pr["category"]
        if cat not in grouped:
            grouped[cat] = []

        rw = rewrite_map.get(pr["number"])
        title = rw["title"] if rw else pr["title"]
        body = rw["body"] if rw else ""

        grouped[cat].append({
            "number": pr["number"],
            "title": title,
            "body": body,
            "url": pr["url"],
            "author": pr["author"],
            "merged_at": pr["merged_at"],
        })

    if fmt == "json":
        result = json.dumps({"repo": repo, "since": since, "grouped": grouped, "total_prs": len(prs)}, indent=2)
        return [TextContent(type="text", text=result)]

    # Markdown format
    lines = [f"# Changelog for {repo}\n", f"*{len(prs)} changes since {since[:10]}*\n"]

    category_labels = {
        "breaking": "Breaking Changes",
        "feature": "New Features",
        "improvement": "Improvements",
        "fix": "Bug Fixes",
        "docs": "Documentation",
        "chore": "Maintenance",
    }
    category_order = ["breaking", "feature", "improvement", "fix", "docs", "chore"]

    for cat in category_order:
        entries = grouped.get(cat, [])
        if not entries:
            continue
        lines.append(f"\n## {category_labels.get(cat, cat.title())}\n")
        for e in entries:
            lines.append(f"- **{e['title']}** ([#{e['number']}]({e['url']})) — @{e['author']}")
            if e.get("body"):
                lines.append(f"  {e['body']}")

    return [TextContent(type="text", text="\n".join(lines))]


async def _rewrite_entry(args: dict) -> list[TextContent]:
    text = args["text"]
    category = args.get("category", "improvement")

    result = await rewriter.rewrite_entry(text, "", category)
    output = f"**{result['title']}**"
    if result.get("body"):
        output += f"\n{result['body']}"

    return [TextContent(type="text", text=output)]


async def _list_recent_prs(args: dict) -> list[TextContent]:
    repo = args["github_repo"]
    since = args.get("since_date")
    token = args.get("github_token")
    max_prs = args.get("max_prs", 20)

    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        prs = await gh.fetch_merged_prs(repo, since=since, token=token, max_prs=max_prs)
    except Exception as e:
        return [TextContent(type="text", text=f"Error fetching PRs: {e}")]

    if not prs:
        return [TextContent(type="text", text=f"No merged PRs found in {repo} since {since}.")]

    lines = [f"## Recent merged PRs in {repo}\n", f"*{len(prs)} PRs since {since[:10]}*\n"]

    # Group summary
    cats: dict[str, int] = {}
    for pr in prs:
        cats[pr["category"]] = cats.get(pr["category"], 0) + 1

    lines.append("**Summary:** " + ", ".join(f"{v} {k}" for k, v in sorted(cats.items(), key=lambda x: -x[1])))
    lines.append("")

    for pr in prs:
        labels_str = f" [{', '.join(pr['labels'])}]" if pr["labels"] else ""
        files_str = f" ({len(pr['files_changed'])} files)" if pr["files_changed"] else ""
        lines.append(f"- **#{pr['number']}** {pr['title']}{labels_str}{files_str}")
        lines.append(f"  Merged {pr['merged_at'][:10]} by @{pr['author']} | Category: {pr['category']}")
        if pr.get("body"):
            body_preview = pr["body"][:150].replace("\n", " ")
            lines.append(f"  > {body_preview}")

    return [TextContent(type="text", text="\n".join(lines))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
