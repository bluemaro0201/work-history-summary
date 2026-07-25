from __future__ import annotations

import base64
import re
from datetime import datetime, timezone as dt_timezone
from html import unescape
from zoneinfo import ZoneInfo

import httpx

from app.collectors.base import PAGINATION_SAFETY_LIMIT, CollectorBase
from app.collectors.git import extract_issue_key
from app.config import settings

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(r"</(p|div|li|h[1-6]|tr|br)\s*>", re.IGNORECASE)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def _html_to_text(value: str) -> str:
    """Confluence storage format is XHTML; strip tags/macros down to readable text."""
    text = _BR_RE.sub("\n", value)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = unescape(text)
    return re.sub(r"[ \t]*\n[ \t]*\n+", "\n\n", text).strip()


class ConfluenceCollector(CollectorBase):
    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]:
        start_utc, end_utc = self.calculate_date_range_utc(date, timezone)
        account_id = user_identity.get("confluence_account_id")
        site_url = options.get("site_url", "").rstrip("/")
        if not site_url:
            return []

        local_tz = ZoneInfo(timezone)
        start_local_date = start_utc.astimezone(local_tz).strftime("%Y-%m-%d")
        end_local_date = end_utc.astimezone(local_tz).strftime("%Y-%m-%d")

        spaces = options.get("spaces", [])
        cql_space = f"space in ({','.join(spaces)}) AND " if spaces else ""
        # Fetch all pages updated on this date; filter locally by user involvement
        cql = f'{cql_space}lastModified >= "{start_local_date}" AND lastModified <= "{end_local_date}" AND type = page'

        is_cloud = user_identity.get("is_cloud", "atlassian.net" in site_url)
        if user_identity.get("auth_type") == "api_token" and is_cloud:
            credentials = base64.b64encode(f"{user_identity.get('email', '')}:{access_token}".encode()).decode()
            headers = {"Authorization": f"Basic {credentials}", "Accept": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

        activities: list[dict] = []
        async with httpx.AsyncClient(base_url=site_url, headers=headers, timeout=settings.collector_timeout_seconds) as client:
            expand = "version,space,comments.body.storage"
            if options.get("include_page_content", True):
                expand += ",body.storage"

            pages: list[dict] = []
            base_url_from_api: str | None = None
            page_size = 25
            offset = 0
            while True:
                params = {"cql": cql, "expand": expand, "limit": page_size, "start": offset}
                data = (await self.with_retry(lambda: client.get("/wiki/rest/api/content", params=params))).json()
                if base_url_from_api is None:
                    base_url_from_api = data.get("_links", {}).get("base", site_url).rstrip("/")
                page_results = data.get("results", [])
                pages.extend(page_results)
                if len(page_results) < page_size or len(pages) >= PAGINATION_SAFETY_LIMIT:
                    break
                offset += len(page_results)

            for page in pages:
                # Exact UTC date post-filter on page modification time
                modified_str = page.get("version", {}).get("when")
                modified: datetime | None = None
                if modified_str:
                    modified = datetime.fromisoformat(modified_str.replace("Z", "+00:00")).astimezone(dt_timezone.utc)

                title = page.get("title")
                webui = page.get("_links", {}).get("webui", "")
                url = (base_url_from_api or site_url) + webui
                project = page.get("space", {}).get("key")
                raw_content = page.get("body", {}).get("storage", {}).get("value") if options.get("include_page_content", True) else None
                page_content = _html_to_text(raw_content) if raw_content else title

                # Case 1: I last modified this page within the date range
                last_editor = page.get("version", {}).get("by", {}).get("accountId")
                if modified and start_utc <= modified < end_utc and (not account_id or last_editor == account_id):
                    activities.append({
                        "source": "confluence", "provider": "confluence",
                        "activity_type": "page_updated",
                        "project": project, "issue_key": extract_issue_key(title),
                        "title": title, "content": page_content,
                        "url": url, "activity_ts": modified_str,
                        "metadata": {"page_id": page.get("id")},
                    })
                    continue  # don't double-count as comment too

                # Case 2: I commented on this page OR was mentioned
                for comment in page.get("comments", {}).get("results", []):
                    comment_body = comment.get("body", {}).get("storage", {})
                    comment_when = comment.get("version", {}).get("when")
                    comment_author = comment.get("version", {}).get("by", {}).get("accountId")
                    comment_time: datetime | None = None
                    if comment_when:
                        comment_time = datetime.fromisoformat(comment_when.replace("Z", "+00:00")).astimezone(dt_timezone.utc)
                    if not (comment_time and start_utc <= comment_time < end_utc):
                        continue
                    raw_body = comment_body.get("value", "")
                    body_value = _html_to_text(raw_body) if raw_body else raw_body
                    if account_id and comment_author == account_id:
                        activities.append({
                            "source": "confluence", "provider": "confluence",
                            "activity_type": "comment",
                            "project": project, "issue_key": extract_issue_key(title),
                            "title": title, "content": body_value,
                            "url": url, "activity_ts": comment_when,
                            "metadata": {"page_id": page.get("id"), "comment_id": comment.get("id")},
                        })
                    elif account_id and account_id in raw_body:
                        activities.append({
                            "source": "confluence", "provider": "confluence",
                            "activity_type": "mention",
                            "project": project, "issue_key": extract_issue_key(title),
                            "title": title, "content": body_value,
                            "url": url, "activity_ts": comment_when,
                            "metadata": {"page_id": page.get("id"), "comment_id": comment.get("id"), "mentioned_by": comment_author},
                        })

        return activities
