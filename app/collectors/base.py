from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

import httpx

# Safety net against runaway pagination (e.g. a misbehaving API never returning has_more=false).
# Not a user-facing limit — a single day's activity should never realistically approach this.
PAGINATION_SAFETY_LIMIT = 3000


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
