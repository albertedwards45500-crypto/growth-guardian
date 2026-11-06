"""真实本地 Qdrant + 假 Embedding，验证持久化、文献生命周期和过滤。"""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient

from app.schemas.advisor import advisor_today
from app.schemas.knowledge import KnowledgeDocument
from app.services.knowledge import KnowledgeStore


class FakeEmbeddings:
    dimensions = 3
    identity = "offline-test-embedding-v1"

    def embed(self, texts):
        return [[0.0, 1.0, 0.0] if "无关" in text else [1.0, 0.0, 0.0] for text in texts]


def document(**overrides):
    return KnowledgeDocument.model_validate({
        "document_id": "test-public-document", "title": "测试公共资料（非医学建议）",
        "content": "这是离线测试资料的完整段落，仅用于验证引用和向量检索。",
        "source_url": "https://example.org/public-guide", "version": "v1",
        "review_status": "approved", "reviewed_by": "测试审核者",
        "reviewed_on": "2026-08-01", "valid_until": (advisor_today() + timedelta(days=365)).isoformat(),
        "scope": "general_education", "topics": ["diet_review", "feeding_knowledge"],
        "age_min_months": 6, "age_max_months": 12, **overrides,
    })


@pytest.fixture()
def store(tmp_path):
    client = QdrantClient(path=str(tmp_path / "vectors"))
    instance = KnowledgeStore(client, FakeEmbeddings(), "test_reviewed_knowledge")
    yield instance
    client.close()


def search(store, **overrides):
    params = {"query": "完整资料", "age_months": 7, "topic": "diet_review",
              "as_of": date(2026, 9, 10), "min_score": 0.5}
    return store.search(**{**params, **overrides})


def test_persistence_idempotency_and_replacement(tmp_path):
    path = str(tmp_path / "persisted")
    client = QdrantClient(path=path)
    store = KnowledgeStore(client, FakeEmbeddings(), "knowledge")
    original = document(content="第一段完整资料用于测试。\n\n第二段完整资料用于测试。")
    assert store.ingest(original) == 2
    store.ingest(original)
    assert client.count("knowledge").count == 2
    client.close()
    client = QdrantClient(path=path)
    store = KnowledgeStore(client, FakeEmbeddings(), "knowledge")
    try:
        assert len(search(store)) == 2
        store.ingest(document(version="v2", content="新版本完整段落替换旧内容。"))
        assert client.count("knowledge").count == 1
        hit = search(store)[0]
        assert hit["text"] == "新版本完整段落替换旧内容。" and hit["version"] == "v2"
        assert hit["url"] == "https://example.org/public-guide"
        store.revoke(original.document_id)
        assert search(store) == []
    finally:
        client.close()


@pytest.mark.parametrize("params", [
    {"age_months": 5}, {"age_months": 13}, {"topic": "growth_review"},
    {"as_of": date(2026, 7, 31)}, {"query": "无关内容"},
])
def test_metadata_and_similarity_filter(store, params):
    store.ingest(document())
    assert search(store)
    assert search(store, **params) == []


def test_current_expiry_also_blocks_historical_retrieval(store):
    from qdrant_client import models

    store.ingest(document())
    store.client.set_payload(store.collection,
                             payload={"valid_until_ordinal": (advisor_today() - timedelta(days=1)).toordinal()},
                             points=models.Filter())
    assert search(store) == []


@pytest.mark.parametrize("overrides", [
    {"review_status": "unverified"}, {"reviewed_by": " "}, {"version": " "},
    {"scope": "private_baby_records"}, {"baby_id": 1}, {"source_url": "file:///private"},
    {"reviewed_on": (advisor_today() + timedelta(days=1)).isoformat()},
    {"valid_until": "2026-01-01"}, {"age_min_months": 15}, {"content": "文" * 1201},
])
def test_reject_unreviewed_private_or_malformed_documents(overrides):
    with pytest.raises(ValidationError):
        document(**overrides)


def test_embedding_signature_and_invalid_vectors_fail_closed(store):
    store.ingest(document())
    store.embedder.identity = "other-model-same-dimensions"
    other = KnowledgeStore(store.client, store.embedder, store.collection)
    with pytest.raises(ValueError, match="不匹配"):
        search(other)
    store.embedder.embed = lambda texts: [[float("nan"), 0, 0] for _ in texts]
    with pytest.raises(ValueError, match="无效"):
        search(store)


def test_failed_embedding_does_not_remove_existing_revision(store):
    store.ingest(document())
    original = search(store)
    embed = store.embedder.embed
    store.embedder.embed = lambda texts: []
    with pytest.raises(ValueError):
        store.ingest(document(version="v2"))
    store.embedder.embed = embed
    assert search(store) == original


def test_empty_index_does_not_call_embedding(store):
    store.embedder.embed = lambda texts: pytest.fail("空索引不能触发外部Embedding")
    assert search(store) == []
