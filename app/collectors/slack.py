from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.collectors.base import CollectorBase
from app.collectors.git import extract_issue_key
from app.config import settings


class SlackCollector(CollectorBase):
    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]:
        start, end = self.calculate_date_range_utc(date, timezone)
        user_id = user_identity.get("slack_user_id")
        headers = {"Authorization": f"Bearer {access_token}"}
        activities: list[dict] = []
        async with httpx.AsyncClient(base_url="https://slack.com/api", headers=headers, timeout=settings.collector_timeout_seconds) as client:
            for channel in options.get("channels", []):
                max_items = options.get("max_activities", settings.collector_max_activities_per_source)
                cursor = None
                channel_messages: list[dict] = []
                while len(channel_messages) < max_items:
                    params: dict = {"channel": channel, "oldest": str(start.timestamp()), "latest": str(end.timestamp()), "inclusive": "true", "limit": min(200, max_items - len(channel_messages))}
                    if cursor:
                        params["cursor"] = cursor
                    data = (await self.with_retry(lambda: client.get("/conversations.history", params=params))).json()
                    channel_messages.extend(data.get("messages", []))
                    meta = data.get("response_metadata", {})
                    cursor = meta.get("next_cursor")
                    if not cursor or not data.get("has_more"):
                        break
                for msg in channel_messages:
                    if not _matches_user(msg, user_id, options):
                        continue
                    activities.append(_message_activity(channel, msg))
                    if options.get("include_threads", True) and msg.get("thread_ts") == msg.get("ts"):
                        replies = (await self.with_retry(lambda: client.get("/conversations.replies", params={"channel": channel, "ts": msg["ts"]}))).json().get("messages", [])[1:]
                        for reply in replies:
                            if _matches_user(reply, user_id, options):
                                activities.append(_message_activity(channel, reply, thread_ts=msg["ts"]))
        return activities[: options.get("max_activities", settings.collector_max_activities_per_source)]


def _matches_user(msg: dict, user_id: str | None, options: dict) -> bool:
    if not user_id:
        return True
    if options.get("only_user_messages", False):
        return msg.get("user") == user_id
    return msg.get("user") == user_id or (options.get("include_mentions", True) and f"<@{user_id}>" in msg.get("text", ""))


def _message_activity(channel: str, msg: dict, thread_ts: str | None = None) -> dict:
    ts = datetime.fromtimestamp(float(msg["ts"]), timezone.utc).isoformat()
    text = msg.get("text", "")
    return {"source": "slack", "provider": "slack", "activity_type": "message", "project": channel, "issue_key": extract_issue_key(text), "title": text[:80] or "Slack message", "content": text, "url": None, "activity_ts": ts, "metadata": {"channel": channel, "thread_ts": thread_ts}}
