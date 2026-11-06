"""接入检查、整批预校验和检索评估；仅使用假服务与临时本地索引。"""

from datetime import timedelta
import json
import logging

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import settings
from app.schemas.advisor import advisor_today
from scripts import check_knowledge, evaluate_knowledge, index_knowledge
from scripts.evaluate_knowledge import EvaluationCase, evaluate_cases
from tests.test_knowledge import document, store  # noqa: F401


@pytest.fixture(autouse=True)
def restore_logging():
    previous = logging.root.manager.disable
    yield
    logging.disable(previous)


def write_json(tmp_path, value):
    target = tmp_path / "public-test.json"
    target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return target


def case(**overrides):
    return EvaluationCase.model_validate({
        "case_id": "public-positive", "query": "完整测试资料", "age_months": 8,
        "topic": "feeding_knowledge", "as_of": "2026-09-10",
        "expected_document_ids": ["test-public-document"], **overrides,
    })


def test_check_configuration_does_not_reuse_chat_key(monkeypatch, capsys):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("offline-chat-secret"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr(""))
    monkeypatch.setattr(check_knowledge, "OpenAIEmbeddings", lambda: pytest.fail("配置不足不能发请求"))
    assert check_knowledge.main(["--probe"]) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["fields"] == ["RAG_EMBEDDING_API_KEY"]
    assert "offline-chat-secret" not in output


@pytest.mark.parametrize("url", ["http://example.org/v1", "https://name:secret@example.org/v1", "https://example.org/v1?api_key=secret"])
def test_check_configuration_rejects_unsafe_endpoint(monkeypatch, url):
    monkeypatch.setattr(settings, "RAG_EMBEDDING_BASE_URL", url)
    assert "RAG_EMBEDDING_BASE_URL" in check_knowledge.check_configuration()


def test_default_check_is_offline_and_probe_uses_only_fixed_text(monkeypatch, capsys):
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr("offline-embedding-secret"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_BASE_URL", "https://embedding.example.org/v1")
    seen = []
    class Embedder:
        def embed(self, texts):
            seen.extend(texts)
            raise RuntimeError("raw-sensitive-provider-error")
    monkeypatch.setattr(check_knowledge, "OpenAIEmbeddings", Embedder)
    assert check_knowledge.main([]) == 0 and not seen
    assert check_knowledge.main(["--probe"]) == 1
    assert seen == ["这是公共知识检索的向量服务连通性测试。"]
    output = capsys.readouterr().out
    assert "embedding_probe_failed" in output
    assert "raw-sensitive-provider-error" not in output and "offline-embedding-secret" not in output


def test_document_check_needs_no_credentials_or_vector_store(tmp_path, monkeypatch, capsys):
    path = write_json(tmp_path, [document().model_dump(mode="json")])
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr(""))
    monkeypatch.setattr(index_knowledge, "get_knowledge_store", lambda: pytest.fail("预校验不得打开索引"))
    index_knowledge.main([str(path), "--check"])
    assert "格式校验通过" in capsys.readouterr().out


@pytest.mark.parametrize("invalid", ["pending", "duplicate", "expired"])
def test_entire_batch_is_checked_before_opening_store(tmp_path, monkeypatch, invalid):
    first = document().model_dump(mode="json")
    second = {**first, "document_id": "other-document"}
    if invalid == "pending":
        second["review_status"] = "pending"
    elif invalid == "duplicate":
        second["document_id"] = first["document_id"]
    else:
        second["valid_until"] = (advisor_today() - timedelta(days=1)).isoformat()
    path = write_json(tmp_path, [first, second])
    monkeypatch.setattr(index_knowledge, "get_knowledge_store", lambda: pytest.fail("整批校验失败不得打开索引"))
    with pytest.raises(ValueError):
        index_knowledge.main([str(path)])


def test_evaluation_metrics_and_age_abstention(store):
    store.ingest(document())
    report = evaluate_cases(store, [case(), case(case_id="too-young", age_months=5,
                                               expected_document_ids=[], expect_empty=True)], 3, .55)
    assert report["status"] == "passed" and report["hit_rate"] == report["mean_recall"] == report["mrr"] == 1
    assert report["empty_result_accuracy"] == 1
    assert "完整测试资料" not in json.dumps(report, ensure_ascii=False)
    assert report["results"][0]["retrieved_document_ids"] == ["test-public-document"]
    store.revoke("test-public-document")
    failed = evaluate_cases(store, [case()], 3, .55)
    assert failed["status"] == "failed" and failed["mean_recall"] == 0


def test_evaluation_forbidden_hits_and_errors_cannot_pass_as_abstention(store):
    store.ingest(document())
    report = evaluate_cases(store, [case(expected_document_ids=["expected-other"],
                                         forbidden_document_ids=["test-public-document"])], 3, .55)
    assert report["status"] == "failed" and report["results"][0]["forbidden_document_ids"]
    class Unavailable:
        def search(self, *args, **kwargs):
            raise RuntimeError("provider-secret")
    report = evaluate_cases(Unavailable(), [case(expected_document_ids=[], expect_empty=True)], 3, .55)
    assert report["status"] == "failed" and report["retrieval_errors"] == 1
    assert report["empty_result_accuracy"] == 0 and "provider-secret" not in json.dumps(report)


def test_evaluation_file_validation_is_offline(tmp_path, monkeypatch, capsys):
    path = write_json(tmp_path, [case().model_dump(mode="json")])
    monkeypatch.setattr(evaluate_knowledge, "get_knowledge_store", lambda: pytest.fail("预校验不能打开索引"))
    assert evaluate_knowledge.main([str(path), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["embedding_called"] is False


@pytest.mark.parametrize("overrides", [
    {"expected_document_ids": []}, {"expect_empty": True},
    {"forbidden_document_ids": ["test-public-document"]}, {"baby_id": 1},
    {"as_of": (advisor_today() + timedelta(days=1)).isoformat()},
])
def test_evaluation_rejects_ambiguous_labels_and_private_context(overrides):
    with pytest.raises(ValidationError):
        case(**overrides)
