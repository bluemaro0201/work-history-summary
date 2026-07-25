import base64

import httpx
from fastapi import APIRouter, HTTPException

from app import providers as prov

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
async def list_providers() -> dict:
    return prov.get_all()


@router.post("/{source}")
async def add_provider(source: str, data: dict) -> dict:
    if source not in prov.SOURCES:
        raise HTTPException(status_code=404, detail="Unsupported source")
    enriched = await _verify_and_enrich(source, data)
    return prov.add(source, enriched)


@router.put("/{source}/{provider_id}")
async def update_provider(source: str, provider_id: str, data: dict) -> dict:
    if source not in prov.SOURCES:
        raise HTTPException(status_code=404, detail="Unsupported source")
    enriched = await _verify_and_enrich(source, data)
    result = prov.update(source, provider_id, enriched)
    if result is None:
        raise HTTPException(status_code=404)
    return result


@router.delete("/{source}/{provider_id}", status_code=204)
async def delete_provider(source: str, provider_id: str) -> None:
    if source not in prov.SOURCES:
        raise HTTPException(status_code=404, detail="Unsupported source")
    if not prov.delete(source, provider_id):
        raise HTTPException(status_code=404)


async def _verify_and_enrich(source: str, data: dict) -> dict:
    """Verify token and auto-populate identity fields (username, user_id, account_id)."""
    token = data.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="토큰을 입력해주세요.")

    try:
        if source == "git":
            return await _verify_git(data, token)

        if source == "slack":
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    "https://slack.com/api/auth.test",
                    headers={"Authorization": f"Bearer {token}"},
                )
            body = res.json()
            if not body.get("ok"):
                raise HTTPException(status_code=400, detail=f"Slack 토큰 검증 실패: {body.get('error', '알 수 없는 오류')}")
            return {**data, "user_id": body.get("user_id", ""), "workspace": body.get("team", "")}

        if source in ("jira", "confluence"):
            site_url = data.get("site_url", "").rstrip("/")
            email = data.get("email", "").strip()
            if not site_url:
                raise HTTPException(status_code=400, detail="사이트 URL을 입력해주세요.")
            is_cloud = "atlassian.net" in site_url
            if is_cloud:
                if not email:
                    raise HTTPException(status_code=400, detail="Cloud 인스턴스는 이메일이 필요합니다.")
                creds = base64.b64encode(f"{email}:{token}".encode()).decode()
                headers = {"Authorization": f"Basic {creds}", "Accept": "application/json"}
                api_path = "/rest/api/3/myself"
            else:
                headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
                api_path = "/rest/api/2/myself"

            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(f"{site_url}{api_path}", headers=headers)
            if not res.is_success:
                raise HTTPException(status_code=400, detail=f"토큰 검증 실패 ({res.status_code}): {res.text[:200]}")
            me = res.json()
            account_id = me.get("accountId") or me.get("key") or me.get("name", "")
            return {**data, "account_id": account_id, "is_cloud": is_cloud}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"검증 중 오류: {exc}") from exc

    return data


async def _verify_git(data: dict, token: str) -> dict:
    host_type = data.get("host_type", "github")
    base_url = (data.get("base_url") or "").rstrip("/")

    if host_type in ("github", "github_enterprise"):
        api_base = base_url if (host_type == "github_enterprise" and base_url) else "https://api.github.com"
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{api_base}/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
        if not res.is_success:
            raise HTTPException(status_code=400, detail=f"GitHub 토큰 검증 실패 ({res.status_code})")
        user = res.json()
        return {**data, "username": user.get("login", ""), "email": user.get("email", "")}

    if host_type == "gitlab":
        api_base = base_url or "https://gitlab.com/api/v4"
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{api_base}/user", headers={"PRIVATE-TOKEN": token})
        if not res.is_success:
            raise HTTPException(status_code=400, detail=f"GitLab 토큰 검증 실패 ({res.status_code})")
        user = res.json()
        return {**data, "username": user.get("username", ""), "email": user.get("email", ""), "account_id": str(user.get("id", ""))}

    if host_type == "bitbucket":
        api_base = base_url or "https://api.bitbucket.org/2.0"
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"{api_base}/user", headers={"Authorization": f"Bearer {token}"})
        if not res.is_success:
            raise HTTPException(status_code=400, detail=f"Bitbucket 토큰 검증 실패 ({res.status_code})")
        user = res.json()
        return {**data, "username": user.get("nickname") or user.get("username", ""), "account_id": user.get("account_id", "")}

    raise HTTPException(status_code=400, detail=f"지원하지 않는 host_type: {host_type}")
