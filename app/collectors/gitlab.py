from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from urllib.parse import quote

import httpx

from app.collectors.base import PAGINATION_SAFETY_LIMIT, CollectorBase
from app.collectors.git import extract_issue_key
from app.config import settings


class GitLabCollector(CollectorBase):
    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]:
        start, end = self.calculate_date_range_utc(date, timezone)
        base_url = options.get("base_url") or "https://gitlab.com/api/v4"
        headers = {"PRIVATE-TOKEN": access_token}
        username = user_identity.get("git_username", "")
        email = user_identity.get("email", "")
        activities: list[dict] = []

        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=settings.collector_timeout_seconds) as client:
            for repo in options.get("repositories", []):
                project_id = quote(repo, safe="")

                if options.get("include_commits", True):
                    # since/until are filtered server-side, so pagination is naturally date-bounded.
                    commits = await self._paginate(
                        client, f"/projects/{project_id}/repository/commits",
                        {"since": start.isoformat(), "until": end.isoformat(), "all": "true"},
                    )
                    for c in commits:
                        # GitLab commits don't expose a GitLab username, so match by author email first
                        if username and c.get("author_email") != email and c.get("author_name") != username:
                            continue
                        message = c.get("message", "")
                        activities.append({
                            "source": "git", "provider": "gitlab", "activity_type": "commit",
                            "project": repo, "issue_key": extract_issue_key(message),
                            "title": message.splitlines()[0] if message else None, "content": message,
                            "url": c.get("web_url"), "activity_ts": c.get("created_at"),
                            "metadata": {"sha": c.get("id")},
                        })

                mrs: list[dict] = []
                if options.get("include_pull_requests", True) or options.get("include_reviews", True):
                    # updated_after/updated_before are filtered server-side too.
                    mrs = await self._paginate(
                        client, f"/projects/{project_id}/merge_requests",
                        {"updated_after": start.isoformat(), "updated_before": end.isoformat(), "scope": "all"},
                    )

                if options.get("include_pull_requests", True):
                    for mr in mrs:
                        author = (mr.get("author") or {}).get("username")
                        created = _parse_dt(mr.get("created_at"))
                        if created and start <= created <= end and (not username or author == username):
                            activities.append(_mr_activity(repo, mr, "pull_request_opened", created))
                        merged = _parse_dt(mr.get("merged_at"))
                        merged_by = (mr.get("merged_by") or {}).get("username")
                        if merged and start <= merged <= end and (not username or merged_by == username):
                            activities.append(_mr_activity(repo, mr, "pull_request_merged", merged))

                if options.get("include_reviews", True):
                    for mr in mrs:
                        iid = mr.get("iid")
                        notes = await self._paginate(client, f"/projects/{project_id}/merge_requests/{iid}/notes", {})
                        for note in notes:
                            if note.get("system"):
                                continue
                            author = (note.get("author") or {}).get("username")
                            if username and author != username:
                                continue
                            created = _parse_dt(note.get("created_at"))
                            if not created or not (start <= created < end):
                                continue
                            activities.append({
                                "source": "git", "provider": "gitlab", "activity_type": "pull_request_commented",
                                "project": repo, "issue_key": extract_issue_key(note.get("body", "")),
                                "title": "Review comment on MR", "content": note.get("body", ""),
                                "url": mr.get("web_url"), "activity_ts": created.isoformat(),
                                "metadata": {"merge_request_iid": iid},
                            })

        return activities

    async def _paginate(self, client: httpx.AsyncClient, url: str, params: dict) -> list[dict]:
        results: list[dict] = []
        page = 1
        while len(results) < PAGINATION_SAFETY_LIMIT:
            resp = await self.with_retry(lambda p=page: client.get(url, params={**params, "per_page": 100, "page": p}))
            batch = resp.json()
            if not batch:
                break
            results.extend(batch)
            next_page = resp.headers.get("X-Next-Page")
            if not next_page:
                break
            page = int(next_page)
        return results


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt_timezone.utc)


def _mr_activity(repo: str, mr: dict, activity_type: str, ts: datetime) -> dict:
    title = mr.get("title")
    return {
        "source": "git", "provider": "gitlab", "activity_type": activity_type,
        "project": repo, "issue_key": extract_issue_key(title), "title": title,
        "content": mr.get("description") or title, "url": mr.get("web_url"),
        "activity_ts": ts.isoformat(), "metadata": {"merge_request_iid": mr.get("iid")},
    }
