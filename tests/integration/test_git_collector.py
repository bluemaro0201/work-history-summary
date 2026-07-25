import httpx
import pytest
import respx

from app.collectors.git import GitHubCollector, extract_issue_key


def test_extract_issue_key():
    assert extract_issue_key("PAYMENT-142 fix retry") == "PAYMENT-142"


@pytest.mark.asyncio
@respx.mock
async def test_git_collector_fetches_commits_with_author_filter():
    route = respx.get("https://api.github.com/repos/org/repo/commits").mock(
        return_value=httpx.Response(200, json=[
            {"sha": "a", "html_url": "https://example", "commit": {"message": "PAY-1 work", "author": {"date": "2026-07-18T01:00:00Z"}}},
        ])
    )

    activities = await GitHubCollector().fetch(
        "2026-07-18", "UTC", {"github_login": "me"}, "token",
        {"repositories": ["org/repo"], "include_pull_requests": False, "include_reviews": False},
    )

    assert route.calls.last.request.url.params["author"] == "me"
    assert activities[0]["source"] == "git"
    assert activities[0]["issue_key"] == "PAY-1"


@pytest.mark.asyncio
@respx.mock
async def test_git_collector_follows_link_header_pagination():
    page1 = httpx.Response(
        200,
        json=[{"sha": "a", "html_url": "https://example/a", "commit": {"message": "first", "author": {"date": "2026-07-18T01:00:00Z"}}}],
        headers={"Link": '<https://api.github.com/repos/org/repo/commits?page=2>; rel="next"'},
    )
    page2 = httpx.Response(
        200,
        json=[{"sha": "b", "html_url": "https://example/b", "commit": {"message": "second", "author": {"date": "2026-07-18T02:00:00Z"}}}],
    )
    respx.get("https://api.github.com/repos/org/repo/commits").mock(side_effect=[page1, page2])

    activities = await GitHubCollector().fetch(
        "2026-07-18", "UTC", {}, "token",
        {"repositories": ["org/repo"], "include_pull_requests": False, "include_reviews": False},
    )

    assert [a["metadata"]["sha"] for a in activities] == ["a", "b"]
