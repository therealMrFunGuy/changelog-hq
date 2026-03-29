"""LLM-based changelog rewriting for ChangelogHQ."""

import os
import httpx
import json
import logging
from typing import Optional

logger = logging.getLogger("changelog-hq.rewriter")

LLM_URL = os.environ.get("LLM_URL", "http://localhost:11435")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "60"))

SYSTEM_PROMPT = """You are a changelog writer. You take developer-oriented pull request information and rewrite it into clear, user-friendly changelog entries.

Rules:
- Write in present tense ("Adds", "Fixes", "Improves")
- Keep entries concise: 1-2 sentences max
- Focus on user impact, not implementation details
- Remove jargon — write for end-users, not developers
- Don't mention file names, function names, or internal code paths
- If a PR is purely internal (CI, tests, refactoring), summarize as a maintenance improvement
- Return ONLY the rewritten entry text, no extra commentary"""

BATCH_PROMPT = """Rewrite these pull request descriptions into user-friendly changelog entries.

For each PR, return a JSON array of objects with this exact structure:
[
  {"number": <pr_number>, "title": "<rewritten title>", "body": "<1-2 sentence description>"}
]

PRs to rewrite:
{prs_text}

Return ONLY the JSON array, nothing else."""


async def rewrite_entry(title: str, body: str, category: str) -> dict:
    """Rewrite a single PR into a user-friendly changelog entry.

    Returns dict with 'title' and 'body' keys.
    Falls back to original if LLM unavailable.
    """
    prompt = f"Category: {category}\nPR Title: {title}\nPR Description: {body[:500]}\n\nRewrite this as a user-friendly changelog entry. Return JSON: {{\"title\": \"...\", \"body\": \"...\"}}"

    try:
        result = await _call_llm(prompt)
        if result:
            parsed = _parse_json(result)
            if parsed and isinstance(parsed, dict) and "title" in parsed:
                return {"title": parsed["title"], "body": parsed.get("body", "")}
    except Exception as e:
        logger.warning(f"LLM rewrite failed: {e}")

    return _fallback_rewrite(title, body)


async def rewrite_batch(prs: list[dict]) -> list[dict]:
    """Rewrite a batch of PRs into user-friendly changelog entries.

    Args:
        prs: List of dicts with 'number', 'title', 'body', 'category' keys

    Returns:
        List of dicts with 'number', 'title', 'body' keys
    """
    if not prs:
        return []

    prs_text = "\n---\n".join(
        f"PR #{p['number']} [{p.get('category', 'improvement')}]: {p['title']}\n{(p.get('body') or '')[:300]}"
        for p in prs
    )
    prompt = BATCH_PROMPT.format(prs_text=prs_text)

    try:
        result = await _call_llm(prompt)
        if result:
            parsed = _parse_json(result)
            if parsed and isinstance(parsed, list):
                # Map results back by PR number
                result_map = {item["number"]: item for item in parsed if isinstance(item, dict) and "number" in item}
                rewritten = []
                for pr in prs:
                    if pr["number"] in result_map:
                        r = result_map[pr["number"]]
                        rewritten.append({
                            "number": pr["number"],
                            "title": r.get("title", pr["title"]),
                            "body": r.get("body", ""),
                        })
                    else:
                        fb = _fallback_rewrite(pr["title"], pr.get("body", ""))
                        rewritten.append({"number": pr["number"], **fb})
                return rewritten
    except Exception as e:
        logger.warning(f"LLM batch rewrite failed: {e}")

    return [
        {"number": p["number"], **_fallback_rewrite(p["title"], p.get("body", ""))}
        for p in prs
    ]


async def _call_llm(prompt: str) -> Optional[str]:
    """Call the Ollama-compatible LLM endpoint."""
    url = f"{LLM_URL}/api/chat"

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1024,
        },
    }

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                if content:
                    return content.strip()

            # Try OpenAI-compatible endpoint as fallback
            openai_url = f"{LLM_URL}/v1/chat/completions"
            openai_payload = {
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 1024,
            }
            resp = await client.post(openai_url, json=openai_payload)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
        except httpx.ConnectError:
            logger.info("LLM endpoint not available, using fallback")
        except Exception as e:
            logger.warning(f"LLM call error: {e}")

    return None


def _parse_json(text: str) -> Optional[dict | list]:
    """Try to extract JSON from LLM response text."""
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    for marker in ["```json", "```"]:
        if marker in text:
            start = text.index(marker) + len(marker)
            end = text.index("```", start) if "```" in text[start:] else len(text)
            try:
                return json.loads(text[start:end].strip())
            except (json.JSONDecodeError, ValueError):
                pass

    # Try finding first { or [
    for ch, end_ch in [("{", "}"), ("[", "]")]:
        idx_start = text.find(ch)
        idx_end = text.rfind(end_ch)
        if idx_start != -1 and idx_end > idx_start:
            try:
                return json.loads(text[idx_start : idx_end + 1])
            except json.JSONDecodeError:
                pass

    return None


def _fallback_rewrite(title: str, body: str) -> dict:
    """Clean up a PR title/body when LLM is unavailable."""
    # Remove common prefixes like "feat:", "fix:", etc.
    clean_title = title.strip()
    for prefix in ["feat:", "fix:", "chore:", "docs:", "refactor:", "perf:", "ci:", "test:",
                    "feat(", "fix(", "chore(", "docs(", "refactor(", "perf("]:
        if clean_title.lower().startswith(prefix):
            if "(" in prefix:
                paren_end = clean_title.find(")")
                if paren_end != -1:
                    clean_title = clean_title[paren_end + 1:].strip().lstrip(":").strip()
            else:
                clean_title = clean_title[len(prefix):].strip()
            break

    # Capitalize first letter
    if clean_title:
        clean_title = clean_title[0].upper() + clean_title[1:]

    # Extract first meaningful sentence from body
    clean_body = ""
    if body:
        lines = body.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("<!--") and len(line) > 10:
                clean_body = line[:200]
                break

    return {"title": clean_title, "body": clean_body}
