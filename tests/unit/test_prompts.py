from app.llm.prompts import SYSTEM_PROMPT, build_user_message


def test_user_message_wraps_activities():
    message = build_user_message("2026-07-18", "Asia/Seoul", {}, [{"content": "UNIQUE_MALICIOUS_PAYLOAD"}])
    assert "<activities>" in message and "</activities>" in message
    assert "UNIQUE_MALICIOUS_PAYLOAD" in message


def test_system_prompt_does_not_contain_activity_data():
    assert "UNIQUE_MALICIOUS_PAYLOAD" not in SYSTEM_PROMPT
