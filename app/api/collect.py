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
    prompt: str
    source_status: list[dict]


@router.post("/collect", response_model=CollectResponse)
async def collect(body: CollectRequest) -> CollectResponse:
    if not body.date:
        raise HTTPException(status_code=400, detail="날짜를 입력해주세요.")

    s = get_settings()
    all_providers = prov.get_all()
    provider_lookup = {p["id"]: {"source": src, **p} for src, items in all_providers.items() for p in items}

    activities: list[dict] = []
    source_status: list[dict] = []

    for sel in body.selections:
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
                collector.fetch(body.date, body.timezone, identity, token, options),
                timeout=s.collector_timeout_seconds,
            )
            activities.extend(fetched)
            source_status.append({"label": p.get("label", source), "source": source, "status": "success", "count": len(fetched)})
        except TimeoutError:
            source_status.append({"label": p.get("label", source), "source": source, "status": "timeout", "count": 0})
        except Exception as exc:
            logger.error("[%s/%s] collection failed: %s", source, p.get("label"), exc, exc_info=True)
            source_status.append({"label": p.get("label", source), "source": source, "status": "failed", "error": str(exc), "count": 0})

    user_msg = build_user_message(body.date, body.timezone, activities)
    return CollectResponse(
        prompt=f"[System]\n{SYSTEM_PROMPT}\n\n[User]\n{user_msg}",
        source_status=source_status,
    )


def _build_identity(p: dict, source: str) -> dict:
    site_url = p.get("site_url", "")
    is_cloud = ("atlassian.net" in site_url) if site_url else True
    return {
        "github_login": p.get("username", ""),
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
    if source == "git" and p.get("repositories"):
        opts["repositories"] = to_list(p["repositories"])
    elif source == "slack" and p.get("channels"):
        opts["channels"] = to_list(p["channels"])
    elif source == "jira" and p.get("projects"):
        opts["projects"] = to_list(p["projects"])
    elif source == "confluence" and p.get("spaces"):
        opts["spaces"] = to_list(p["spaces"])
    return opts
