from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone

import httpx

from app.collectors.base import PAGINATION_SAFETY_LIMIT, CollectorBase
from app.config import settings

JIRA_KEY_PATTERN = re.compile(r"[A-Z]+-\d+")


def extract_issue_key(text: str | None) -> str | None:
    if not text:
        return None
    match = JIRA_KEY_PATTERN.search(text)
    return match.group(0) if match else None


class GitHubCollector(CollectorBase):
    """Handles both GitHub.com and GitHub Enterprise (same API shape, different base_url)."""

    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]:
        start, end = self.calculate_date_range_utc(date, timezone)
        base_url = options.get("base_url") or "https://api.github.com"
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
        activities: list[dict] = []
        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=settings.collector_timeout_seconds) as client:
            for repo in options.get("repositories", []):
                if options.get("include_commits", True):
                    # since/until are filtered server-side, so pagination is naturally date-bounded.
                    params = {"since": start.isoformat(), "until": end.isoformat()}
                    if options.get("git_user_field", "author") == "author" and user_identity.get("github_login"):
                        params["author"] = user_identity["github_login"]
                    commits = await self._paginate(client, f"/repos/{repo}/commits", params)
                    for commit in commits:
                        message = commit.get("commit", {}).get("message", "")
                        activities.append({"source": "git", "provider": "github", "activity_type": "commit", "project": repo, "issue_key": extract_issue_key(message), "title": message.splitlines()[0] if message else None, "content": message, "url": commit.get("html_url"), "activity_ts": commit.get("commit", {}).get("author", {}).get("date"), "metadata": {"sha": commit.get("sha")}})
                if options.get("include_pull_requests", True):
                    # Not date-filtered server-side; sorted by updated desc, so we can stop once
                    # an item's updated_at falls before our range (everything after is even older).
                    pulls = await self._paginate(
                        client, f"/repos/{repo}/pulls", {"state": "all", "sort": "updated", "direction": "desc"},
                        stop_when=lambda pr: (dt := _parse_dt(pr.get("updated_at"))) is not None and dt < start,
                    )
                    login = user_identity.get("github_login")
                    for pr in pulls:
                        created = _parse_dt(pr.get("created_at"))
                        merged = _parse_dt(pr.get("merged_at"))
                        if login and pr.get("user", {}).get("login") == login and created and start <= created <= end:
                            activities.append(_pr_activity(repo, pr, "pull_request_opened", created))
                        if merged and start <= merged <= end and (not login or pr.get("merged_by", {}).get("login") == login):
                            activities.append(_pr_activity(repo, pr, "pull_request_merged", merged))
                if options.get("include_reviews", True):
                    login = user_identity.get("github_login")
                    # since= with direction=asc returns comments oldest-first from start, so we
                    # can stop once we pass the end of our range.
                    comments = await self._paginate(
                        client, f"/repos/{repo}/pulls/comments", {"since": start.isoformat(), "direction": "asc"},
                        stop_when=lambda c: (dt := _parse_dt(c.get("created_at"))) is not None and dt > end,
                    )
                    for comment in comments:
                        if login and comment.get("user", {}).get("login") != login:
                            continue
                        created = _parse_dt(comment.get("created_at"))
                        if not created or not (start <= created < end):
                            continue
                        pr_url = comment.get("pull_request_url", "")
                        activities.append({"source": "git", "provider": "github", "activity_type": "pull_request_commented", "project": repo, "issue_key": extract_issue_key(comment.get("body", "")), "title": f"Review comment on PR", "content": comment.get("body", ""), "url": comment.get("html_url"), "activity_ts": created.isoformat(), "metadata": {"pull_request_url": pr_url, "path": comment.get("path")}})
        return activities

    async def _paginate(self, client: httpx.AsyncClient, url: str, params: dict, stop_when: Callable[[dict], bool] | None = None) -> list[dict]:
        results: list[dict] = []
        next_url: str | None = url
        next_params: dict | None = {**params, "per_page": 100}
        while next_url and len(results) < PAGINATION_SAFETY_LIMIT:
            resp = await self.with_retry(lambda u=next_url, p=next_params: client.get(u, params=p))
            batch = resp.json()
            if not isinstance(batch, list):
                break
            for item in batch:
                if stop_when and stop_when(item):
                    return results
                results.append(item)
            next_url = resp.links.get("next", {}).get("url")
            next_params = None
        return results


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _pr_activity(repo: str, pr: dict, activity_type: str, ts: datetime) -> dict:
    title = pr.get("title")
    return {"source": "git", "provider": "github", "activity_type": activity_type, "project": repo, "issue_key": extract_issue_key(title), "title": title, "content": pr.get("body") or title, "url": pr.get("html_url"), "activity_ts": ts.isoformat(), "metadata": {"pull_request_url": pr.get("html_url"), "number": pr.get("number")}}
