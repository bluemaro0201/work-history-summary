from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

import httpx

from app.collectors.base import CollectorBase
from app.config import settings

logger = logging.getLogger(__name__)


class JiraCollector(CollectorBase):
    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]:
        start_utc, end_utc = self.calculate_date_range_utc(date, timezone)
        account_id = user_identity.get("jira_account_id")
        site_url = options.get("site_url", "").rstrip("/")
        if not site_url:
            return []

        local_tz = ZoneInfo(timezone)
        start_local_date = start_utc.astimezone(local_tz).strftime("%Y-%m-%d")
        end_local_date = end_utc.astimezone(local_tz).strftime("%Y-%m-%d")

        projects = options.get("projects", [])
        project_clause = f"project in ({','.join(projects)}) AND " if projects else ""
        # Fetch all issues updated on this date in the project; filter locally by user involvement
        jql = f'{project_clause}updated >= "{start_local_date}" AND updated <= "{end_local_date}" ORDER BY updated DESC'

        if user_identity.get("auth_type") == "api_token" and user_identity.get("is_cloud"):
            credentials = base64.b64encode(f"{user_identity.get('email', '')}:{access_token}".encode()).decode()
            headers = {"Authorization": f"Basic {credentials}", "Accept": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        activities: list[dict] = []
        async with httpx.AsyncClient(base_url=site_url, headers=headers, timeout=settings.collector_timeout_seconds) as client:
            issues: list[dict] = []
            page_size = 50
            start_at = 0
            while True:
                try:
                    resp = await self.with_retry(lambda: client.get(
                        "/rest/api/3/search/jql",
                        params={"jql": jql, "expand": "changelog", "fields": "summary,comment,updated,assignee,status", "startAt": start_at, "maxResults": page_size},
                    ))
                except httpx.HTTPStatusError as e:
                    logger.error("[jira] search failed %s: %s", e.response.status_code, e.response.text[:500])
                    raise
                data = resp.json()
                page = data.get("issues", [])
                issues.extend(page)
                if len(page) < page_size or len(issues) >= options.get("max_activities", settings.collector_max_activities_per_source):
                    break
                start_at += len(page)

            for issue in issues:
                fields = issue.get("fields", {})
                key = issue.get("key")
                title = fields.get("summary")
                project = (key or "").split("-")[0]
                issue_url = f"{site_url}/browse/{key}"
                is_assignee = account_id and (fields.get("assignee") or {}).get("accountId") == account_id
                issue_activities: list[dict] = []

                for history in issue.get("changelog", {}).get("histories", []):
                    if account_id and history.get("author", {}).get("accountId") != account_id:
                        continue
                    created = _parse_jira_dt(history.get("created"))
                    if created and start_utc <= created < end_utc:
                        changed = ", ".join(item.get("field", "field") for item in history.get("items", []))
                        issue_activities.append({"source": "jira", "provider": "jira", "activity_type": "changelog", "project": project, "issue_key": key, "title": title, "content": f"Changed: {changed}", "url": issue_url, "activity_ts": created.isoformat(), "metadata": {"fields": history.get("items", [])}})

                for comment in fields.get("comment", {}).get("comments", []):
                    created = _parse_jira_dt(comment.get("created"))
                    if not (created and start_utc <= created < end_utc):
                        continue
                    author_id = comment.get("author", {}).get("accountId")
                    body = comment.get("body", {})
                    mentioned = account_id and _is_mentioned(body, account_id)
                    if account_id and author_id == account_id:
                        issue_activities.append({"source": "jira", "provider": "jira", "activity_type": "comment", "project": project, "issue_key": key, "title": title, "content": _extract_text(body), "url": issue_url, "activity_ts": created.isoformat(), "metadata": {"comment_id": comment.get("id")}})
                    elif mentioned:
                        issue_activities.append({"source": "jira", "provider": "jira", "activity_type": "mention", "project": project, "issue_key": key, "title": title, "content": _extract_text(body), "url": issue_url, "activity_ts": created.isoformat(), "metadata": {"comment_id": comment.get("id"), "mentioned_by": author_id}})

                # Assigned but no direct activity found → record as issue_updated
                if not issue_activities and is_assignee:
                    updated = _parse_jira_dt(fields.get("updated"))
                    if updated and start_utc <= updated < end_utc:
                        status = fields.get("status", {}).get("name", "")
                        issue_activities.append({"source": "jira", "provider": "jira", "activity_type": "issue_updated", "project": project, "issue_key": key, "title": title, "content": f"Status: {status}", "url": issue_url, "activity_ts": updated.isoformat(), "metadata": {}})

                activities.extend(issue_activities)

        return activities[: options.get("max_activities", settings.collector_max_activities_per_source)]


def _parse_jira_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt_timezone.utc)


def _is_mentioned(adf: dict | str, account_id: str) -> bool:
    """Recursively check Atlassian Document Format for a mention of account_id."""
    if not isinstance(adf, dict):
        return False
    if adf.get("type") == "mention" and adf.get("attrs", {}).get("id") == account_id:
        return True
    return any(_is_mentioned(child, account_id) for child in adf.get("content", []))


def _extract_text(adf: dict | str) -> str:
    """Extract plain text from Atlassian Document Format."""
    if isinstance(adf, str):
        return adf
    if not isinstance(adf, dict):
        return ""
    if adf.get("type") == "text":
        return adf.get("text", "")
    return " ".join(_extract_text(child) for child in adf.get("content", [])).strip()
