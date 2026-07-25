---
name: work-summary
description: Collect the user's daily work activity from configured Git/Slack/Jira/Confluence providers (via this repo's collectors) and write a Korean daily work report directly in the conversation. Use when the user asks for "오늘/어제 업무 요약", "일일 업무 보고서", "work summary", "daily report", or similar for this project.
---

## Prerequisites (check these first)

1. `data/providers.json` must exist with at least one provider token. If it doesn't exist, tell the user to run the web UI once and configure tokens there — don't ask them to paste tokens into this conversation. Either works:
   - Python: `poetry run uvicorn app.main:app --reload`
   - Docker: `docker compose up`

   then open `http://localhost:8000/settings`. Stop here until that's done.
2. Dependencies must be installed. If `poetry run python -c "import httpx"` fails, run `poetry install` first.

## Steps

1. Determine the target date (default: today) and timezone (default: `Asia/Seoul`) — ask the user only if ambiguous.
2. Optionally ask which sources to include (git/slack/jira/confluence). Default: all configured providers.
3. From the repository root, run:
   ```
   PYTHONPATH=. poetry run python "${CLAUDE_SKILL_DIR}/scripts/collect.py" --date <YYYY-MM-DD> --timezone <tz> [--sources git,slack,...]
   ```
   This reuses the exact same collection and prompt-building logic as the web UI (`app/api/collect.py`), so results are identical to what `/api/collect` + `/api/prompt` would produce.
4. Parse the JSON on stdout: `{"prompt": "...", "source_status": [...], "activity_count": N}`.
   - If it's `{"error": "..."}` instead, relay that message to the user and stop.
   - Check `source_status` for entries with `status` other than `"success"` (e.g. `no_token`, `timeout`, `failed`) and mention them briefly so the user knows what's missing.
5. The `prompt` field is a full `[System]\n...\n\n[User]\n...` instruction block — the same one a user would otherwise paste into a separate Claude/ChatGPT chat. Follow those instructions yourself and write the report directly in this conversation, in Korean, using only the data in the `[User]` section (don't invent anything not present there).
6. Before finalizing, ask the user if they want to exclude anything or manually add an item that wasn't auto-collected (mirrors the web UI's activity-selection step), and revise the report accordingly.
