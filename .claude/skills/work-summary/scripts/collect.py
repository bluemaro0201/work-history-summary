"""CLI used by the work-summary skill.

Reuses the same collection + prompt-building logic as the web UI
(app/api/collect.py) so behavior never drifts between the two entry points.
Run from the repo root with PYTHONPATH=. — see SKILL.md for the exact command.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app import providers as prov
from app.api.collect import ProviderSelection, build_prompt_text, collect_activities


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--timezone", default="Asia/Seoul")
    parser.add_argument("--sources", default="", help="Comma-separated filter: git,slack,jira,confluence (default: all configured providers)")
    args = parser.parse_args()

    wanted = {s.strip() for s in args.sources.split(",") if s.strip()}
    all_providers = prov.get_all()
    selections = [
        ProviderSelection(provider_id=p["id"], source=src, enabled=True)
        for src, items in all_providers.items() if not wanted or src in wanted
        for p in items
    ]

    if not selections:
        print(json.dumps({"error": "설정된 provider가 없습니다. 먼저 웹 UI(/settings)에서 토큰을 등록하세요."}, ensure_ascii=False))
        sys.exit(1)

    activities, source_status = await collect_activities(args.date, args.timezone, selections)
    prompt = build_prompt_text(args.date, args.timezone, activities)
    print(json.dumps({"prompt": prompt, "source_status": source_status, "activity_count": len(activities)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
