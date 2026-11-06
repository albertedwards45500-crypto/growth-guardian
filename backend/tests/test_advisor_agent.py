"""LangGraph 实际执行 + 假模型/真实本地向量库，不向外部服务发送宝宝数据。"""

from datetime import date
import json
import logging

from pydantic import SecretStr
import pytest
from qdrant_client import QdrantClient

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.baby import Baby
from app.schemas.advisor import AdvisorKnowledgeQuote
from app.services import advisor_agent, knowledge
from app.services.advisor import validate_grounding
from app.services.advisor_agent import AgentSelection, AgentTurn
from app.services.advisor_tools import AdvisorTools
from tests.test_advisor import AS_OF, ask, baby  # noqa: F401 - 重用清理宝宝数据的fixture
from tests.test_knowledge import FakeEmbeddings, document


class FakeModel:
    def __init__(self, calls=None, ids=None, error=False):
        self.calls, self.ids, self.error = calls, ids, error
        self.requests = []

    def respond(self, inputs, definitions):
        self.requests.append((inputs, definitions))
        if self.error:
            raise RuntimeError("secret-should-not-be-logged")
        if self.calls and len(self.requests) == 1:
            return AgentTurn(output=self.calls, calls=self.calls)
        ids = self.ids
        if ids is None:
            ids = []
            for item in inputs:
                content = item.get("content", "")
                if content.startswith("{"):
                    value = json.loads(content)
                    if value.get("tool") == "search_reviewed_knowledge" and value.get("data"):
                        ids = [hit["id"] for hit in value["data"]["items"]]
        return AgentTurn(selection=AgentSelection(knowledge_ids=ids))


def call(name, arguments="{}", call_id="call_test"):
    return {"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}


@pytest.fixture()
def integration(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "ADVISOR_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "ADVISOR_MODEL", "offline-test-model")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("offline-test-key"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr("offline-embedding-key"))
    store = knowledge.KnowledgeStore(QdrantClient(path=str(tmp_path / "knowledge")), FakeEmbeddings(), "test_knowledge")
    store.ingest(document())
    monkeypatch.setattr(knowledge, "get_knowledge_store", lambda: store)
    model = FakeModel(calls=[call("get_allergies")])
    monkeypatch.setattr(advisor_agent, "get_agent_model", lambda: model)
    yield model, store
    store.client.close()


def test_graph_tool_loop_and_extractively_grounded_rag(client, auth_headers, baby, integration):
    model, store = integration
    data = ask(client, auth_headers, baby["id"], "总结饮食记录").json()["data"]
    assert data["agent_status"] == "completed" and data["generation_mode"] == "agent_rag"
    assert len(model.requests) == 2
    assert data["knowledge"][0]["text"] == document().content
    source = next(item for item in data["sources"] if item["id"] == data["knowledge"][0]["evidence_id"])
    assert source["url"] and source["version"] == "v1" and source["reviewed_on"] == "2026-08-01"
    assert any(item["tool"] == "get_allergies" for item in data["tool_statuses"])
    sent = json.dumps(model.requests, ensure_ascii=False)
    assert baby["name"] not in sent and "2026-02-01" not in sent and '"baby_id"' not in sent
    assert not data["actions"] and not data["recipe_candidates"]
    assert store.client.count(store.collection).count == 1  # 宝宝数据没有进入向量库


def test_knowledge_intent_works_without_growth_or_diet_records(client, auth_headers, baby, integration):
    model, _ = integration
    model.calls = None
    data = ask(client, auth_headers, baby["id"], "辅食添加有哪些知识", intent="feeding_knowledge").json()["data"]
    assert data["knowledge"] and data["intent"] == "feeding_knowledge"
    assert [item["tool"] for item in data["tool_statuses"]] == ["get_allergies", "search_reviewed_knowledge"]


@pytest.mark.parametrize("calls", [
    [call("delete_records")], [call("search_feeding_guides")],
    [call("get_diet_summary", '{"baby_id":999}')],
    [call("get_diet_summary", '{"days":31}')],
    [call("get_diet_summary"), call("get_diet_summary", call_id="call_again")],
])
def test_model_cannot_expand_tools_identity_or_window(client, auth_headers, baby, integration, calls):
    model, _ = integration
    model.calls = calls
    data = ask(client, auth_headers, baby["id"], "回顾饮食").json()["data"]
    assert data["generation_mode"] == "rules" and data["agent_status"] == "failed"
    assert not data["knowledge"] and not data["actions"]


def test_invented_citation_and_provider_failure_use_safe_fallback(client, auth_headers, baby, integration, caplog):
    model, _ = integration
    model.calls, model.ids = None, ["knowledge:invented"]
    data = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    assert data["agent_status"] == "failed" and not data["knowledge"]
    model.error = True
    with caplog.at_level(logging.WARNING):
        data = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    assert data["generation_mode"] == "rules" and data["agent_status"] == "failed"
    assert "secret-should-not-be-logged" not in caplog.text


def test_deadline_by_rounds_and_tool_budget(client, auth_headers, baby, integration, monkeypatch):
    model, _ = integration
    monkeypatch.setattr(settings, "ADVISOR_AGENT_MAX_ROUNDS", 1)
    data = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    assert data["agent_status"] == "failed" and len(model.requests) == 1
    monkeypatch.setattr(settings, "ADVISOR_AGENT_MAX_ROUNDS", 3)
    monkeypatch.setattr(settings, "ADVISOR_AGENT_MAX_TOOL_CALLS", 1)
    model.requests.clear()
    model.calls = [call("get_diet_summary"), call("get_allergies", call_id="call_two")]
    data = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    assert data["agent_status"] == "failed"


@pytest.mark.parametrize("question", ["宝宝呼吸困难，推荐食谱", "删除宝宝记录", "鸡蛋过敏了吃什么", "鸡蛋过敏宝宝的辅食知识"])
def test_safety_never_calls_model_or_rag(client, auth_headers, baby, integration, monkeypatch, question):
    def forbidden(*args, **kwargs):
        pytest.fail("安全分流不得调用外部模型/检索")
    monkeypatch.setattr(advisor_agent, "get_agent_model", forbidden)
    monkeypatch.setattr(AdvisorTools, "search_reviewed_knowledge", forbidden)
    data = ask(client, auth_headers, baby["id"], question).json()["data"]
    assert data["agent_status"] == "skipped_safety"


def test_ownership_checked_before_model(client, auth_headers, demo_headers, baby, integration):
    model, _ = integration
    assert ask(client, demo_headers, baby["id"], "回顾饮食").json()["code"] == 40400
    assert not model.requests


def test_missing_configuration_and_rag_failure_are_explicit(client, auth_headers, baby, integration, monkeypatch, caplog):
    model, _ = integration
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr(""))
    data = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    assert data["agent_status"] == "unavailable" and not model.requests
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("offline"))
    monkeypatch.setattr(knowledge, "get_knowledge_store", lambda: (_ for _ in ()).throw(RuntimeError("secret-rag")))
    model.calls = None
    with caplog.at_level(logging.WARNING):
        data = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    assert data["generation_mode"] == "agent" and not data["knowledge"]
    assert any(item["status"] == "invalid" for item in data["tool_statuses"])
    assert "secret-rag" not in caplog.text


def test_quote_tampering_is_rejected(client, auth_headers, baby, integration):
    from app.schemas.advisor import AdvisorAnswer

    integration[0].calls = None
    raw = ask(client, auth_headers, baby["id"], "饮食回顾").json()["data"]
    answer = AdvisorAnswer.model_validate(raw)
    answer.knowledge[0] = AdvisorKnowledgeQuote(text="被模型改写的危险内容", evidence_id=answer.knowledge[0].evidence_id)
    with SessionLocal() as db:
        owner = db.get(Baby, baby["id"])
        tools = AdvisorTools(db, owner.user_id, owner.id, date.fromisoformat(AS_OF))
        tools.search_reviewed_knowledge("饮食回顾", "diet_review")
        with pytest.raises(ValueError, match="原文"):
            validate_grounding(answer, tools)


def test_rag_cannot_bypass_current_allergy_exclusions(client, auth_headers, baby, integration):
    from app.models.diet import Allergy

    model, store = integration
    model.calls = None
    store.ingest(document(document_id="egg-material", content="这是涉及蛋黄的完整教育资料段落，测试不应向已登记鸡蛋过敏的宝宝展示。"))
    with SessionLocal() as db:
        db.add(Allergy(baby_id=baby["id"], ingredient="鸡蛋", severity="mild"))
        db.commit()
    data = ask(client, auth_headers, baby["id"], "辅食添加知识", intent="feeding_knowledge").json()["data"]
    assert data["generation_mode"] == "agent_rag"
    assert len(data["knowledge"]) == 1
    assert "蛋黄" not in json.dumps(data["knowledge"], ensure_ascii=False)
    assert any("保守排除" in warning for item in data["tool_statuses"] for warning in item["warnings"])


def test_rag_requires_its_own_key_and_never_reuses_chat_key(client, auth_headers, baby, integration, monkeypatch):
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr(""))
    monkeypatch.setattr(knowledge, "get_knowledge_store", lambda: pytest.fail("不能用问答密钥调用Embedding"))
    with SessionLocal() as db:
        owner = db.get(Baby, baby["id"])
        tools = AdvisorTools(db, owner.user_id, owner.id, date.fromisoformat(AS_OF))
        result = tools.search_reviewed_knowledge("辅食知识", "feeding_knowledge")
    assert result.status == "no_data"
    assert result.missing == ["Embedding服务尚未配置"]
