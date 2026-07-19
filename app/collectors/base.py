from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

import httpx


@runtime_checkable
class Collector(Protocol):
    async def fetch(self, date: str, timezone: str, user_identity: dict, access_token: str, options: dict) -> list[dict]: ...


class CollectorBase:
    def calculate_date_range_utc(self, date: str, timezone: str) -> tuple[datetime, datetime]:
        local_zone = ZoneInfo(timezone)
        local_date = datetime.fromisoformat(date).date()
        start_local = datetime.combine(local_date, time.min, tzinfo=local_zone)
        # Use next day 00:00:00 (exclusive) per PRD spec rather than 23:59:59.999999
        end_local = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=local_zone)
        return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)

    async def fetch_all_pages(self, client: httpx.AsyncClient, url: str, params: dict, items_key: str, next_cursor_key: str | None = None, max_items: int = 500) -> list[dict]:
        results: list[dict] = []
        cursor = params.get("cursor")
        while len(results) < max_items:
            request_params = dict(params)
            if cursor:
                request_params["cursor"] = cursor
            response = await self.with_retry(lambda: client.get(url, params=request_params))
            data = response.json()
            items = data if isinstance(data, list) else data.get(items_key, [])
            results.extend(items)
            if not next_cursor_key or isinstance(data, list):
                break
            cursor = data.get(next_cursor_key) or data.get("response_metadata", {}).get(next_cursor_key)
            if not cursor:
                break
        return results[:max_items]

    async def with_retry(self, operation: Callable[[], Awaitable[httpx.Response]], max_retries: int = 3) -> httpx.Response:
        for attempt in range(max_retries + 1):
            response = await operation()
            if response.status_code == 429 and attempt < max_retries:
                await asyncio.sleep(_retry_after(response, attempt))
                continue
            if 500 <= response.status_code < 600 and attempt < max_retries:
                await asyncio.sleep(2**attempt * 2)
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("unreachable retry state")


def _retry_after(response: httpx.Response, attempt: int) -> int:
    retry_after = response.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return int(retry_after)
    reset = response.headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        return max(0, int(reset) - int(datetime.now(dt_timezone.utc).timestamp()))
    return 2**attempt * 5
