"""隔离草稿预览：使用假Embedding和真实内存Qdrant，不调用外部服务。"""

from datetime import timedelta
import json
import logging
from pathlib import Path

import pytest

from app.core.config import settings
from app.schemas.advisor import advisor_today
from scripts import preview_candidates
from scripts.check_candidates import load_candidates
from scripts.evaluate_knowledge import EvaluationCase, evaluate_cases, load_cases
from scripts.preview_candidates import CandidatePreviewStore, evaluate_preview, validate_preview_inputs
from tests.test_knowledge import FakeEmbeddings


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "docs" / "knowledge.candidates.json"
CASES = ROOT / "docs" / "knowledge-evaluation.draft.json"


@pytest.fixture(autouse=True)
def restore_logging():
    previous = logging.root.manager.disable
    yield
    logging.disable(previous)


@pytest.fixture
def store():
    instance = CandidatePreviewStore(FakeEmbeddings())
    yield instance
    instance.close()


def honey():
    return next(item for item in load_candidates(CANDIDATES) if item.document_id == "nhs_honey_under_12_months")


def case(**overrides):
    return EvaluationCase.model_validate({
        "case_id": "preview-test", "query": "蜂蜜测试", "age_months": 8,
        "topic": "recipe_recommendation", "as_of": advisor_today(),
        "expected_document_ids": [honey().document_id], **overrides,
    })


def test_preview_keeps_pending_and_never_opens_configured_store(store, monkeypatch):
    monkeypatch.setattr(settings, "QDRANT_URL", "https://must-not-open.invalid")
    monkeypatch.setattr(settings, "QDRANT_PATH", "must-not-create")
    item = honey()
    assert store.ingest([item]) == 1
    points, _ = store.client.scroll(store.collection)
    assert points[0].payload["review_status"] == "pending"
    assert item.review_status == "pending"
    assert not {"text", "content", "source_excerpt", "reviewed_on"} & points[0].payload.keys()
    report = evaluate_cases(store, [case()], 3, .55)
    assert report["status"] == "passed"
    assert report["results"][0]["retrieved_document_ids"] == [item.document_id]


@pytest.mark.parametrize("age,expected", [(0, True), (11, True), (12, False), (36, False)])
def test_preview_honey_age_boundaries(store, age, expected):
    store.ingest([honey()])
    hits = store.search("蜂蜜", age, "recipe_recommendation", advisor_today())
    assert bool(hits) is expected


def test_preview_excludes_wrong_topic_old_date_and_irrelevant_query(store):
    item = honey()
    store.ingest([item])
    assert store.search("蜂蜜", 8, "growth_review", advisor_today()) == []
    assert store.search("蜂蜜", 8, "feeding_knowledge", item.source_checked_on - timedelta(days=1)) == []
    assert store.search("无关", 8, "feeding_knowledge", advisor_today()) == []


@pytest.mark.parametrize("overrides", [
    {"expected_document_ids": ["unknown"]}, {"forbidden_document_ids": ["unknown"]},
    {"age_months": 12}, {"topic": "growth_review"},
    {"as_of": "2020-01-01"},
])
def test_preview_rejects_unknown_and_impossible_positive_labels(overrides):
    with pytest.raises(ValueError):
        validate_preview_inputs([honey()], [case(**overrides)])


def test_source_unchecked_candidates_cannot_be_previewed(store):
    item = honey().model_copy(update={"source_checked_on": None, "source_excerpt": None, "source_section": None})
    with pytest.raises(ValueError):
        store.ingest([item])
    assert store.embedding_requests == 0


def test_full_bundle_check_is_offline_and_does_not_open_any_index(monkeypatch, capsys):
    monkeypatch.setattr(preview_candidates, "CandidatePreviewStore", lambda *_: pytest.fail("不得打开索引"))
    monkeypatch.setattr(preview_candidates, "OpenAIEmbeddings", lambda: pytest.fail("不得调用服务"))
    validate_preview_inputs(load_candidates(CANDIDATES), load_cases(CASES))
    assert preview_candidates.main([str(CANDIDATES), str(CASES), "--check"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "valid", "documents": 5, "cases": 17,
        "embedding_called": False, "index_opened": False,
    }


def test_preview_report_is_sanitized_and_resources_closed(tmp_path, monkeypatch, capsys):
    class Embedder(FakeEmbeddings):
        model = "offline-test-model"
    instances = []
    class Store(CandidatePreviewStore):
        closed = False
        def __init__(self, embedder):
            super().__init__(embedder)
            instances.append(self)
        def close(self):
            self.closed = True
            super().close()
    monkeypatch.setattr(preview_candidates, "OpenAIEmbeddings", Embedder)
    monkeypatch.setattr(preview_candidates, "CandidatePreviewStore", Store)
    monkeypatch.setattr(preview_candidates, "check_configuration", lambda: [])
    output = tmp_path / "report.json"
    # 假向量让无答案语义用例失败；失败也必须如实写报告，不能伪称全通过。
    assert preview_candidates.main([str(CANDIDATES), str(CASES), "--output", str(output)]) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "failed" and report["production_index_opened"] is False
    assert report["application_rag_modified"] is False
    assert report["candidate_review_status"] == "pending" and report["index_storage"] == "memory"
    assert report["embedding_requests"] == 18 and report["embedded_texts"] == 22
    assert len(report["candidate_sha256"]) == len(report["cases_sha256"]) == 64
    assert instances[0].closed
    assert "source_excerpt" not in capsys.readouterr().out
    assert not any(item.query in output.read_text(encoding="utf-8") for item in load_cases(CASES))


def test_preview_closes_on_provider_failure(monkeypatch):
    instances = []
    class FailingStore:
        def __init__(self, *_):
            self.closed = False
            instances.append(self)
        def ingest(self, *_):
            raise RuntimeError("provider-private-message")
        def close(self):
            self.closed = True
    monkeypatch.setattr(preview_candidates, "CandidatePreviewStore", FailingStore)
    monkeypatch.setattr(preview_candidates, "check_configuration", lambda: [])
    with pytest.raises(RuntimeError):
        preview_candidates.main([str(CANDIDATES), str(CASES)])
    assert instances[0].closed


def test_threshold_comparison_reuses_vectors_and_keeps_baseline_status(tmp_path, monkeypatch, capsys):
    class Embedder(FakeEmbeddings):
        model = "offline-test-model"
    monkeypatch.setattr(preview_candidates, "OpenAIEmbeddings", Embedder)
    monkeypatch.setattr(preview_candidates, "check_configuration", lambda: [])
    monkeypatch.setattr(settings, "RAG_MIN_SCORE", .55)
    output = tmp_path / "comparison.json"
    assert preview_candidates.main([str(CANDIDATES), str(CASES), "--output", str(output),
                                    "--compare-thresholds", ".60", ".65", ".65"]) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["min_score"] == settings.RAG_MIN_SCORE == .55
    assert [item["min_score"] for item in report["threshold_comparison"]] == [.6, .65]
    assert report["embedding_requests"] == 18 and report["embedded_texts"] == 22
    assert report["status"] == "failed"
    assert all("retrieved_document_scores" in item for item in report["results"])
    assert json.loads(capsys.readouterr().out)["report_saved"] is True


def test_diagnostics_do_not_reuse_previous_hit_on_failure():
    class Store:
        calls = 0
        def search(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("private-provider-error")
            return [{"document_id": honey().document_id, "score": .75}]
    report = evaluate_preview(Store(), [case(), case(case_id="failed-query")], 3, .55)
    assert report["results"][0]["retrieved_document_scores"][0]["score"] == .75
    assert report["results"][1]["retrieved_document_scores"] == []
    assert report["results"][1]["retrieval_failed"] is True
    assert "private-provider-error" not in json.dumps(report)


@pytest.mark.parametrize("value", ["nan", "inf", "1.1"])
def test_thresholds_are_validated_before_network(value, monkeypatch):
    monkeypatch.setattr(preview_candidates, "OpenAIEmbeddings", lambda: pytest.fail("不得调用服务"))
    with pytest.raises(ValueError):
        preview_candidates.main([str(CANDIDATES), str(CASES), "--compare-thresholds", value])


@pytest.mark.parametrize("output", [".env", "docs/knowledge.candidates.json", "docs/knowledge-evaluation.draft.json"])
def test_report_cannot_overwrite_inputs_or_secrets(output, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(preview_candidates, "OpenAIEmbeddings", lambda: pytest.fail("不得调用服务"))
    with pytest.raises(ValueError):
        preview_candidates.main([str(CANDIDATES), str(CASES), "--output", output])
