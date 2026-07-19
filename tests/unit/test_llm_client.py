import httpx
import pytest

from app.llm.client import LLMClient, _extract_hermes_text


def test_extract_hermes_text_supports_common_shapes():
    assert _extract_hermes_text({"output": "a"}) == "a"
    assert _extract_hermes_text({"message": {"content": "b"}}) == "b"
    assert _extract_hermes_text({"choices": [{"message": {"content": "c"}}]}) == "c"


@pytest.mark.asyncio
async def test_hermes_client_posts_system_and_user_message(monkeypatch):
    captured = {}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(200, json={"output": "{\"completed\": [\"ok\"]}"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    client = LLMClient(provider="hermes", model="hermes-agent", hermes_agent_url="http://hermes.local/complete", hermes_api_key="secret")
    text = await client.complete("hello")

    assert "completed" in text
    assert captured["url"] == "http://hermes.local/complete"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "hermes-agent"
    assert captured["json"]["system"]
    assert captured["json"]["messages"] == [{"role": "user", "content": "hello"}]
