from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone as dt_timezone

import httpx

from app.collectors.base import PAGINATION_SAFETY_LIMIT, CollectorBase
from app.collectors.git import extract_issue_key
from app.config import settings


class BitbucketCollector(CollectorBase):
    """Bitbucket Cloud only. Auth is Bearer-token based (repository/workspace access token or Atlassian API token)."""

    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]:
        start, end = self.calculate_date_range_utc(date, timezone)
        base_url = options.get("base_url") or "https://api.bitbucket.org/2.0"
        headers = {"Authorization": f"Bearer {access_token}"}
        username = user_identity.get("git_username", "")
        account_id = user_identity.get("git_account_id", "")
        activities: list[dict] = []

        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=settings.collector_timeout_seconds) as client:
            for repo in options.get("repositories", []):
                if options.get("include_commits", True):
                    # Not date-filtered server-side; default order is newest-first, so we can
                    # stop once an item's date falls before our range.
                    commits = await self._paginate(
                        client, f"/repositories/{repo}/commits", {},
                        stop_when=lambda c: (dt := _parse_dt(c.get("date"))) is not None and dt < start,
                    )
                    for c in commits:
                        created = _parse_dt(c.get("date"))
                        if not created or not (start <= created < end):
                            continue
                        if not _is_me(c.get("author", {}).get("user") or {}, account_id, username):
                            continue
                        message = c.get("message", "")
                        activities.append({
                            "source": "git", "provider": "bitbucket", "activity_type": "commit",
                            "project": repo, "issue_key": extract_issue_key(message),
                            "title": message.splitlines()[0] if message else None, "content": message,
                            "url": (c.get("links", {}).get("html") or {}).get("href"),
                            "activity_ts": c.get("date"), "metadata": {"sha": c.get("hash")},
                        })

                prs: list[dict] = []
                if options.get("include_pull_requests", True) or options.get("include_reviews", True):
                    prs = await self._paginate(
                        client, f"/repositories/{repo}/pullrequests", {"state": "ALL", "sort": "-updated_on"},
                        stop_when=lambda pr: (dt := _parse_dt(pr.get("updated_on"))) is not None and dt < start,
                    )

                if options.get("include_pull_requests", True):
                    for pr in prs:
                        mine = _is_me(pr.get("author", {}), account_id, username)
                        created = _parse_dt(pr.get("created_on"))
                        if created and start <= created < end and mine:
                            activities.append(_pr_activity(repo, pr, "pull_request_opened", created))
                        if pr.get("state") == "MERGED" and mine:
                            # Bitbucket's PR list doesn't reliably expose who merged it, so this
                            # only catches merges of PRs the user authored.
                            updated = _parse_dt(pr.get("updated_on"))
                            if updated and start <= updated < end:
                                activities.append(_pr_activity(repo, pr, "pull_request_merged", updated))

                if options.get("include_reviews", True):
                    for pr in prs:
                        pr_id = pr.get("id")
                        comments = await self._paginate(client, f"/repositories/{repo}/pullrequests/{pr_id}/comments", {})
                        for comment in comments:
                            if comment.get("deleted") or not _is_me(comment.get("user", {}), account_id, username):
                                continue
                            created = _parse_dt(comment.get("created_on"))
                            if not created or not (start <= created < end):
                                continue
                            body = (comment.get("content") or {}).get("raw", "")
                            activities.append({
                                "source": "git", "provider": "bitbucket", "activity_type": "pull_request_commented",
                                "project": repo, "issue_key": extract_issue_key(body),
                                "title": "Review comment on PR", "content": body,
                                "url": (comment.get("links", {}).get("html") or {}).get("href"),
                                "activity_ts": created.isoformat(), "metadata": {"pull_request_id": pr_id},
                            })

        return activities

    async def _paginate(self, client: httpx.AsyncClient, url: str, params: dict, stop_when: Callable[[dict], bool] | None = None) -> list[dict]:
        results: list[dict] = []
        next_url: str | None = url
        next_params: dict | None = {**params, "pagelen": 100}
        while next_url and len(results) < PAGINATION_SAFETY_LIMIT:
            resp = await self.with_retry(lambda u=next_url, p=next_params: client.get(u, params=p))
            data = resp.json()
            for item in data.get("values", []):
                if stop_when and stop_when(item):
                    return results
                results.append(item)
            next_url = data.get("next")
            next_params = None
        return results


def _is_me(actor: dict, account_id: str, username: str) -> bool:
    if not account_id and not username:
        return True
    if account_id and actor.get("account_id") == account_id:
        return True
    return bool(username) and actor.get("nickname") == username


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt_timezone.utc)


def _pr_activity(repo: str, pr: dict, activity_type: str, ts: datetime) -> dict:
    title = pr.get("title")
    return {
        "source": "git", "provider": "bitbucket", "activity_type": activity_type,
        "project": repo, "issue_key": extract_issue_key(title), "title": title,
        "content": (pr.get("summary") or {}).get("raw") or title,
        "url": (pr.get("links", {}).get("html") or {}).get("href"),
        "activity_ts": ts.isoformat(), "metadata": {"pull_request_id": pr.get("id")},
    }
