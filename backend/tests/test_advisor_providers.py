"""通过真实 SDK 和内存 HTTP 传输核对 Responses/Embedding 协议，无外部请求。"""

import json

import httpx
import openai
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services.advisor_agent import ResponsesModel
from app.services.knowledge import OpenAIEmbeddings


def sdk_client(monkeypatch, handler):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("offline-test-key"))
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr(settings, "ADVISOR_MODEL", "offline-test-model")
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr("offline-embedding-key"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    original = openai.OpenAI
    def factory(**kwargs):
        return original(**{**kwargs, "http_client": httpx.Client(transport=httpx.MockTransport(handler))})
    monkeypatch.setattr(openai, "OpenAI", factory)


def envelope(output):
    return {"id": "resp_offline", "object": "response", "created_at": 1,
            "model": "offline-model", "status": "completed", "output": output}


def test_responses_function_call_and_reasoning_replay(monkeypatch):
    seen = []
    reasoning = {"type": "reasoning", "id": "rs_test", "summary": []}
    call = {"type": "function_call", "id": "fc_test", "call_id": "call_test",
            "name": "get_diet_summary", "arguments": "{}", "status": "completed"}
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path == "/v1/responses"
        assert body["store"] is False and body["parallel_tool_calls"] is False
        assert body["text"]["format"]["strict"] is True
        if len(seen) == 1:
            return httpx.Response(200, json=envelope([reasoning, call]))
        assert body["input"][0]["type"] == "reasoning"
        assert body["input"][2]["type"] == "function_call_output"
        return httpx.Response(200, json=envelope([{
            "id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": '{"knowledge_ids":[]}', "annotations": []}],
        }]))
    sdk_client(monkeypatch, handler)
    model = ResponsesModel()
    turn = model.respond([{"role": "user", "content": "离线问题"}], [])
    assert turn.calls[0]["name"] == "get_diet_summary"
    final = model.respond(turn.output + [{"type": "function_call_output", "call_id": "call_test", "output": "{}"}], [])
    assert final.selection.knowledge_ids == [] and len(seen) == 2


def test_provider_rate_limit_has_no_automatic_retries(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(429, json={"error": {"message": "offline limit", "type": "rate_limit_error"}})
    sdk_client(monkeypatch, handler)
    with pytest.raises(openai.RateLimitError):
        ResponsesModel().respond([{"role": "user", "content": "离线问题"}], [])
    assert len(seen) == 1


@pytest.mark.parametrize("send_dimensions", [True, False])
def test_embedding_batch_indices_are_sorted_and_request_is_float(monkeypatch, send_dimensions):
    def handler(request):
        assert request.url.host == "api.openai.com"
        assert request.headers["authorization"] == "Bearer offline-embedding-key"
        body = json.loads(request.content)
        assert request.url.path == "/v1/embeddings"
        assert body["encoding_format"] == "float"
        assert ("dimensions" in body) == send_dimensions
        if send_dimensions:
            assert body["dimensions"] == 3
        assert body["input"] == ["第一段公共知识", "第二段公共知识"]
        return httpx.Response(200, json={"object": "list", "model": "offline-embedding", "data": [
            {"index": 1, "object": "embedding", "embedding": [0., 1., 0.]},
            {"index": 0, "object": "embedding", "embedding": [1., 0., 0.]},
        ], "usage": {"prompt_tokens": 1, "total_tokens": 1}})
    sdk_client(monkeypatch, handler)
    # 即使问答使用 DeepSeek，也不能将其密钥/地址用于 Embedding。
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("offline-deepseek-chat-key"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_DIMENSIONS", 3)
    monkeypatch.setattr(settings, "RAG_EMBEDDING_SEND_DIMENSIONS", send_dimensions)
    embedder = OpenAIEmbeddings()
    assert embedder.embed(["第一段公共知识", "第二段公共知识"]) == [[1., 0., 0.], [0., 1., 0.]]


def test_embedding_rejects_wrong_provider_dimensions(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"object": "list", "model": "offline-embedding", "data": [
            {"index": 0, "object": "embedding", "embedding": [1., 0.]},
        ], "usage": {"prompt_tokens": 1, "total_tokens": 1}})
    sdk_client(monkeypatch, handler)
    monkeypatch.setattr(settings, "RAG_EMBEDDING_DIMENSIONS", 3)
    with pytest.raises(ValueError, match="向量无效"):
        OpenAIEmbeddings().embed(["公共测试文本"])
