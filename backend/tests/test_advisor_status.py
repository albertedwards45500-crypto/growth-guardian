"""顾问配置状态只暴露功能标记，且始终校验登录和宝宝归属。"""

from datetime import date

import pytest
from pydantic import SecretStr

from app.core.config import settings
from tests.test_advisor import baby  # noqa: F401


def test_status_requires_owner(client, auth_headers, demo_headers, baby):
    path = f"/api/v1/babies/{baby['id']}/advisor/status"
    assert client.get(path).json()["code"] == 40100
    assert client.get(path, headers=demo_headers).json()["code"] == 40400
    assert client.get("/api/v1/babies/999999/advisor/status", headers=auth_headers).json()["code"] == 40400
    assert client.get(path, headers=auth_headers).json()["code"] == 0


@pytest.mark.parametrize("agent_enabled,rag_enabled,chat_key,embedding_key,model,expected", [
    (False, False, "", "", "", ("disabled", "disabled")),
    (True, True, "", "", "test-model", ("unconfigured", "unconfigured")),
    (True, True, "fake-chat-secret", "", "test-model", ("configured", "unconfigured")),
    (True, True, "fake-chat-secret", "fake-embedding-secret", " ", ("unconfigured", "configured")),
    (True, True, "fake-chat-secret", "fake-embedding-secret", "test-model", ("configured", "configured")),
])
def test_status_is_configuration_only(client, auth_headers, baby, monkeypatch,
                                      agent_enabled, rag_enabled, chat_key, embedding_key, model, expected):
    monkeypatch.setattr(settings, "ADVISOR_AGENT_ENABLED", agent_enabled)
    monkeypatch.setattr(settings, "RAG_ENABLED", rag_enabled)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr(chat_key))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr(embedding_key))
    monkeypatch.setattr(settings, "ADVISOR_MODEL", model)
    # 配置足够即可返回；无需实际访问模型服务或打开向量索引。
    response = client.get(f"/api/v1/babies/{baby['id']}/advisor/status", headers=auth_headers)
    data = response.json()["data"]
    assert set(data) == {"agent", "knowledge", "today"}
    assert (data["agent"], data["knowledge"]) == expected
    assert date.fromisoformat(data["today"])
    assert "fake-chat-secret" not in response.text
    assert "fake-embedding-secret" not in response.text
    assert "test-model" not in response.text
