import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import providers as prov
from app.collectors import COLLECTORS
from app.config import get_settings
from app.llm.prompts import SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["collect"])


class ProviderSelection(BaseModel):
    provider_id: str
    source: str
    enabled: bool = True


class CollectRequest(BaseModel):
    date: str
    timezone: str = "Asia/Seoul"
    selections: list[ProviderSelection] = []


class CollectResponse(BaseModel):
    activities: list[dict]
    source_status: list[dict]


class PromptRequest(BaseModel):
    date: str
    timezone: str = "Asia/Seoul"
    activities: list[dict] = []


class PromptResponse(BaseModel):
    prompt: str


async def collect_activities(date: str, timezone: str, selections: list[ProviderSelection]) -> tuple[list[dict], list[dict]]:
    """Shared by the /api/collect endpoint and the work-summary skill's CLI script."""
    s = get_settings()
    all_providers = prov.get_all()
    provider_lookup = {p["id"]: {"source": src, **p} for src, items in all_providers.items() for p in items}

    activities: list[dict] = []
    source_status: list[dict] = []

    for sel in selections:
        if not sel.enabled:
            continue

        p = provider_lookup.get(sel.provider_id)
        if not p:
            source_status.append({"label": "?", "source": sel.source, "status": "not_found", "count": 0})
            continue

        source = p["source"]
        collector = COLLECTORS.get(source)
        if not collector:
            continue

        token = p.get("token", "")
        if not token:
            source_status.append({"label": p.get("label", source), "source": source, "status": "no_token", "count": 0})
            continue

        identity = _build_identity(p, source)
        options = _build_options(p, source)

        try:
            fetched = await asyncio.wait_for(
                collector.fetch(date, timezone, identity, token, options),
                timeout=s.collector_timeout_seconds,
            )
            activities.extend(fetched)
            source_status.append({"label": p.get("label", source), "source": source, "status": "success", "count": len(fetched)})
        except TimeoutError:
            source_status.append({"label": p.get("label", source), "source": source, "status": "timeout", "count": 0})
        except Exception as exc:
            logger.error("[%s/%s] collection failed: %s", source, p.get("label"), exc, exc_info=True)
            source_status.append({"label": p.get("label", source), "source": source, "status": "failed", "error": str(exc), "count": 0})

    return activities, source_status


def build_prompt_text(date: str, timezone: str, activities: list[dict]) -> str:
    """Shared by the /api/prompt endpoint and the work-summary skill's CLI script."""
    user_msg = build_user_message(date, timezone, activities)
    return f"[System]\n{SYSTEM_PROMPT}\n\n[User]\n{user_msg}"


@router.post("/collect", response_model=CollectResponse)
async def collect(body: CollectRequest) -> CollectResponse:
    if not body.date:
        raise HTTPException(status_code=400, detail="날짜를 입력해주세요.")
    activities, source_status = await collect_activities(body.date, body.timezone, body.selections)
    return CollectResponse(activities=activities, source_status=source_status)


@router.post("/prompt", response_model=PromptResponse)
async def build_prompt(body: PromptRequest) -> PromptResponse:
    return PromptResponse(prompt=build_prompt_text(body.date, body.timezone, body.activities))


def _build_identity(p: dict, source: str) -> dict:
    site_url = p.get("site_url", "")
    is_cloud = ("atlassian.net" in site_url) if site_url else True
    return {
        "github_login": p.get("username", ""),
        "git_username": p.get("username", ""),
        "git_account_id": p.get("account_id", "") if source == "git" else "",
        "slack_user_id": p.get("user_id", ""),
        "jira_account_id": p.get("account_id", "") if source == "jira" else "",
        "confluence_account_id": p.get("account_id", "") if source == "confluence" else "",
        "email": p.get("email", ""),
        "auth_type": "api_token",
        "is_cloud": is_cloud,
        "git_emails": [],
    }


def _build_options(p: dict, source: str) -> dict:
    def to_list(val: str) -> list[str]:
        return [x.strip() for x in (val or "").split(",") if x.strip()]

    opts: dict = {}
    if source in ("jira", "confluence"):
        opts["site_url"] = p.get("site_url", "")
    if source == "git":
        opts["host_type"] = p.get("host_type", "github")
        if p.get("base_url"):
            opts["base_url"] = p["base_url"]
        if p.get("repositories"):
            opts["repositories"] = to_list(p["repositories"])
    elif source == "slack" and p.get("channels"):
        opts["channels"] = to_list(p["channels"])
    elif source == "jira" and p.get("projects"):
        opts["projects"] = to_list(p["projects"])
    elif source == "confluence" and p.get("spaces"):
        opts["spaces"] = to_list(p["spaces"])
    return opts
