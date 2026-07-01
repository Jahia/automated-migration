from __future__ import annotations

import logging
import os
import re

import httpx

from .config import settings
from .models import GitHubComment, GitHubIssue

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def parse_issue_ref(ref: str, default_repo: str | None = None) -> tuple[str, int]:
    if "#" not in ref:
        raise ValueError(f"Invalid issue ref: {ref}")
    parts = ref.split("#")
    repo = parts[0] if parts[0] else default_repo
    if not repo:
        raise ValueError(f"No repo specified in ref: {ref}")
    return repo, int(parts[1])


class GitHubClient:
    def __init__(self, token: str | None = None):
        self.token = token or settings.github_token or os.environ.get("GITHUB_TOKEN")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.http = httpx.AsyncClient(base_url=GITHUB_API, headers=headers, timeout=30)

    async def fetch_issue(self, repo: str, number: int) -> GitHubIssue:
        resp = await self.http.get(f"/repos/{repo}/issues/{number}")
        resp.raise_for_status()
        data = resp.json()

        comments = []
        if data.get("comments", 0) > 0:
            comments_resp = await self.http.get(
                f"/repos/{repo}/issues/{number}/comments",
                params={"per_page": 100},
            )
            if comments_resp.status_code == 200:
                for c in comments_resp.json()[:5]:
                    comments.append(
                        GitHubComment(
                            author=c.get("user", {}).get("login", "unknown"),
                            body=truncate(c.get("body", ""), 1000),
                            created_at=c.get("created_at", ""),
                        )
                    )

        return GitHubIssue(
            ref=f"{repo}#{number}",
            number=number,
            title=data.get("title", ""),
            body=truncate(data.get("body", "") or "", 3000),
            state=data.get("state", ""),
            labels=[l["name"] for l in data.get("labels", [])[:10]],
            comments=comments,
            url=data.get("html_url", ""),
        )

    async def fetch_issues(self, refs: list[str], default_repo: str | None = None) -> list[GitHubIssue]:
        results = []
        for ref in refs:
            try:
                repo, number = parse_issue_ref(ref, default_repo)
                issue = await self.fetch_issue(repo, number)
                results.append(issue)
            except Exception as e:
                log.warning(f"Failed to fetch issue {ref}: {e}")
                results.append(
                    GitHubIssue(
                        ref=ref,
                        number=0,
                        title=f"[Failed to fetch: {ref}]",
                        body=str(e),
                        state="unknown",
                        url="",
                    )
                )
        return results


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
