"""GitHub API integration for ChangelogHQ."""

import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional

GITHUB_API = "https://api.github.com"

# Label-to-category mapping
LABEL_CATEGORIES = {
    "feature": "feature",
    "enhancement": "feature",
    "new feature": "feature",
    "feat": "feature",
    "bug": "fix",
    "fix": "fix",
    "bugfix": "fix",
    "hotfix": "fix",
    "improvement": "improvement",
    "refactor": "improvement",
    "perf": "improvement",
    "performance": "improvement",
    "breaking": "breaking",
    "breaking change": "breaking",
    "breaking-change": "breaking",
    "docs": "docs",
    "documentation": "docs",
    "chore": "chore",
    "ci": "chore",
    "test": "chore",
    "tests": "chore",
    "dependencies": "chore",
    "deps": "chore",
}

CATEGORY_ORDER = ["breaking", "feature", "improvement", "fix", "docs", "chore"]
CATEGORY_LABELS = {
    "breaking": "Breaking Changes",
    "feature": "New Features",
    "improvement": "Improvements",
    "fix": "Bug Fixes",
    "docs": "Documentation",
    "chore": "Maintenance",
}


def _headers(token: Optional[str] = None) -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def classify_pr(labels: list[str], title: str) -> str:
    """Classify a PR into a category based on labels and title."""
    for label in labels:
        normalized = label.lower().strip()
        if normalized in LABEL_CATEGORIES:
            return LABEL_CATEGORIES[normalized]

    title_lower = title.lower()
    if any(kw in title_lower for kw in ["fix", "bug", "patch", "hotfix"]):
        return "fix"
    if any(kw in title_lower for kw in ["feat", "add", "new", "implement"]):
        return "feature"
    if any(kw in title_lower for kw in ["breaking", "deprecat", "remov"]):
        return "breaking"
    if any(kw in title_lower for kw in ["doc", "readme"]):
        return "docs"
    if any(kw in title_lower for kw in ["refactor", "improv", "updat", "enhanc", "optim", "perf"]):
        return "improvement"

    return "improvement"


async def fetch_merged_prs(
    repo: str,
    since: Optional[str] = None,
    token: Optional[str] = None,
    max_prs: int = 50,
) -> list[dict]:
    """Fetch merged PRs from a GitHub repo.

    Args:
        repo: owner/repo format (e.g. 'vercel/next.js')
        since: ISO date string to fetch PRs merged after this date
        token: Optional GitHub token for private repos / higher rate limits
        max_prs: Maximum number of PRs to return
    """
    if not since:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    prs = []
    page = 1

    async with httpx.AsyncClient(timeout=30) as client:
        while len(prs) < max_prs:
            resp = await client.get(
                f"{GITHUB_API}/repos/{repo}/pulls",
                params={
                    "state": "closed",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": min(100, max_prs),
                    "page": page,
                },
                headers=_headers(token),
            )
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            for pr in data:
                if not pr.get("merged_at"):
                    continue
                if pr["merged_at"] < since:
                    # PRs are sorted by updated desc; once merged_at < since we may still
                    # find newer ones if they were recently updated, so continue scanning
                    continue

                labels = [l["name"] for l in pr.get("labels", [])]
                category = classify_pr(labels, pr["title"])

                files_changed = []
                try:
                    files_resp = await client.get(
                        f"{GITHUB_API}/repos/{repo}/pulls/{pr['number']}/files",
                        params={"per_page": 30},
                        headers=_headers(token),
                    )
                    if files_resp.status_code == 200:
                        files_changed = [f["filename"] for f in files_resp.json()]
                except Exception:
                    pass

                prs.append({
                    "number": pr["number"],
                    "title": pr["title"],
                    "body": pr.get("body") or "",
                    "url": pr["html_url"],
                    "author": pr["user"]["login"] if pr.get("user") else "unknown",
                    "labels": labels,
                    "category": category,
                    "files_changed": files_changed,
                    "merged_at": pr["merged_at"],
                })

                if len(prs) >= max_prs:
                    break

            # Stop if we've gone past our since date for all items on the page
            oldest_updated = data[-1].get("updated_at", "") if data else ""
            if oldest_updated and oldest_updated < since:
                break

            page += 1
            if page > 10:
                break

    prs.sort(key=lambda x: x["merged_at"], reverse=True)
    return prs


async def fetch_repo_info(repo: str, token: Optional[str] = None) -> Optional[dict]:
    """Fetch basic repo information."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"{GITHUB_API}/repos/{repo}",
                headers=_headers(token),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "name": data["name"],
                "full_name": data["full_name"],
                "description": data.get("description", ""),
                "stars": data.get("stargazers_count", 0),
                "url": data["html_url"],
            }
        except Exception:
            return None
