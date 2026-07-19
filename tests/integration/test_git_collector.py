import pytest

from app.collectors.git import GitCollector, extract_issue_key


def test_extract_issue_key():
    assert extract_issue_key("PAYMENT-142 fix retry") == "PAYMENT-142"


@pytest.mark.asyncio
async def test_git_collector_fetches_commits(monkeypatch):
    async def fake_fetch_all_pages(self, client, url, params, items_key, next_cursor_key=None, max_items=500):
        assert url == "/repos/org/repo/commits"
        assert params["author"] == "me"
        return [{"sha": "a", "html_url": "https://example", "commit": {"message": "PAY-1 work", "author": {"date": "2026-07-18T01:00:00Z"}}}]

    monkeypatch.setattr(GitCollector, "fetch_all_pages", fake_fetch_all_pages)
    activities = await GitCollector().fetch("2026-07-18", "UTC", {"github_login": "me"}, "token", {"repositories": ["org/repo"], "include_pull_requests": False, "include_reviews": False})
    assert activities[0]["source"] == "git"
    assert activities[0]["issue_key"] == "PAY-1"
