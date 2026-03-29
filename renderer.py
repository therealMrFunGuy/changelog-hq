"""HTML/Markdown/RSS rendering for ChangelogHQ."""

import os
from datetime import datetime
from typing import Optional
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)


def render_changelog_html(project: dict, grouped_entries: dict[str, list[dict]],
                          theme: str = "auto") -> str:
    """Render a full changelog HTML page."""
    template = _env.get_template("changelog.html")
    return template.render(
        project=project,
        grouped=grouped_entries,
        category_order=["breaking", "feature", "improvement", "fix", "docs", "chore"],
        category_labels={
            "breaking": "Breaking Changes",
            "feature": "New Features",
            "improvement": "Improvements",
            "fix": "Bug Fixes",
            "docs": "Documentation",
            "chore": "Maintenance",
        },
        theme=theme,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )


def render_changelog_markdown(project: dict, grouped_entries: dict[str, list[dict]]) -> str:
    """Render changelog as Markdown."""
    lines = [f"# Changelog - {project['name']}\n"]

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
        entries = grouped_entries.get(cat, [])
        if not entries:
            continue
        lines.append(f"\n## {category_labels.get(cat, cat.title())}\n")
        for e in entries:
            pr_link = f" ([#{e['pr_number']}]({e['pr_url']}))" if e.get("pr_number") else ""
            lines.append(f"- **{e['title']}**{pr_link}")
            if e.get("body"):
                lines.append(f"  {e['body']}")

    return "\n".join(lines)


def render_rss_feed(project: dict, entries: list[dict], base_url: str = "") -> str:
    """Render an Atom RSS feed for a project's changelog."""
    project_id = project["id"]
    feed_url = f"{base_url}/projects/{project_id}/feed.xml"
    html_url = f"{base_url}/projects/{project_id}/changelog"

    items = []
    for entry in entries[:50]:
        pub_date = entry.get("created_at", datetime.utcnow().isoformat())
        cat_emoji = {
            "feature": "&#x2728;",
            "fix": "&#x1F41B;",
            "improvement": "&#x1F680;",
            "breaking": "&#x26A0;",
            "docs": "&#x1F4D6;",
            "chore": "&#x1F527;",
        }.get(entry.get("category", ""), "")

        content = f"<p>{entry.get('body', '')}</p>"
        if entry.get("pr_url"):
            content += f'<p><a href="{entry["pr_url"]}">View PR #{entry.get("pr_number", "")}</a></p>'

        items.append(f"""  <entry>
    <title>{cat_emoji} {_xml_escape(entry['title'])}</title>
    <id>urn:changelog:{project_id}:{entry['id']}</id>
    <updated>{pub_date}</updated>
    <author><name>{_xml_escape(entry.get('author', 'unknown'))}</name></author>
    <category term="{entry.get('category', 'improvement')}" />
    <content type="html">{_xml_escape(content)}</content>
  </entry>""")

    updated = entries[0]["created_at"] if entries else datetime.utcnow().isoformat()

    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Changelog - {_xml_escape(project['name'])}</title>
  <subtitle>Latest changes for {_xml_escape(project.get('repo', ''))}</subtitle>
  <link href="{feed_url}" rel="self" type="application/atom+xml" />
  <link href="{html_url}" rel="alternate" type="text/html" />
  <id>urn:changelog:{project_id}</id>
  <updated>{updated}</updated>
  <generator>ChangelogHQ</generator>
{chr(10).join(items)}
</feed>"""


def render_widget_js(project: dict, entries: list[dict], base_url: str = "") -> str:
    """Render an embeddable widget JavaScript snippet."""
    template = _env.get_template("widget.html")
    recent = entries[:5]
    return template.render(
        project=project,
        entries=recent,
        base_url=base_url,
        entry_count=len(entries),
    )


def _xml_escape(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
