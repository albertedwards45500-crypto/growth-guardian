"""重复检索诊断只使用假向量服务及内存索引。"""

import json
import logging
from pathlib import Path

import pytest

from app.core.config import settings
from app.schemas.advisor import advisor_today
from scripts import check_retrieval_stability as stability
from scripts.check_candidates import load_candidates
from scripts.evaluate_knowledge import EvaluationCase, load_cases
from scripts.preview_candidates import validate_preview_inputs
from tests.test_knowledge import FakeEmbeddings


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "docs/knowledge.candidates.json"
CHALLENGE = ROOT / "docs/knowledge-evaluation.challenge.json"
REGRESSION = ROOT / "docs/knowledge-evaluation.draft.json"


@pytest.fixture(autouse=True)
def restore_logging():
    previous = logging.root.manager.disable
    yield
    logging.disable(previous)


def corpus():
    return [next(item for item in load_candidates(CANDIDATES) if item.document_id == "nhs_honey_under_12_months")]


def case(case_id="positive", query="固定公开问题仅用于离线测试", **overrides):
    return EvaluationCase.model_validate({
        "case_id": case_id, "query": query, "age_months": 8, "topic": "feeding_knowledge",
        "as_of": advisor_today(), "expected_document_ids": [corpus()[0].document_id], **overrides,
    })


def cases():
    return [case(), case(case_id="empty", query="无关的固定公开问题", expected_document_ids=[], expect_empty=True)]


class Embedder(FakeEmbeddings):
    model = "offline-test-model"


def run(embedder=None, **overrides):
    return stability.run_stability(corpus(), cases(), [], embedder or Embedder(),
                                   **{"repeats": 3, "top_k": 3, "min_score": .55, **overrides})


def test_repeat_rebuild_and_singleton_stability_without_production_store(monkeypatch):
    monkeypatch.setattr(settings, "QDRANT_URL", "https://do-not-open.invalid")
    monkeypatch.setattr(settings, "QDRANT_PATH", "must-not-create")
    report = run(single_probe_ids=["positive"])
    assert report["status"] == "passed" and report["retrieval_stable"]
    assert report["embedding_vectors_identical"] and report["embedding_changed_inputs"] == 0
    assert report["cloud_embedding_requests"] == 6 and report["cloud_embedded_texts"] == 12
    assert report["production_index_opened"] is False and report["application_rag_modified"] is False
    assert report["repeats_evaluated"] == 3
    assert all(item["same_index_replay_stable"] and item["rebuilt_index_replay_stable"] for item in report["runs"])
    assert all(item["singleton_probes"][0]["matches_batch_retrieval"] for item in report["runs"])
    assert report["candidate_review_status"] == "pending"
    rendered = json.dumps(report, ensure_ascii=False)
    assert not any(item.query in rendered for item in cases())
    assert corpus()[0].content not in rendered
    assert all(len(sample["vector_sha256"]) == 64 for item in report["vector_fingerprints"] for sample in item["samples"])


def test_embedding_changes_are_separate_from_label_and_index_failures():
    class Drifting(Embedder):
        calls = 0
        def embed(self, texts):
            self.calls += 1
            vectors = super().embed(texts)
            return [[0., 1., 0.] if self.calls > 1 and text == case().query else vector
                    for text, vector in zip(texts, vectors)]
    report = run(Drifting())
    assert report["status"] == "failed" and report["retrieval_stable"] is False
    assert report["changed_case_ids"] == ["positive"]
    assert report["failed_case_ids"] == ["positive"]
    assert report["embedding_changed_inputs"] == 1 and not report["embedding_vectors_identical"]
    assert all(item["same_index_replay_stable"] for item in report["runs"])


def test_vector_scaling_drift_does_not_claim_changed_retrieval():
    class Scaling(Embedder):
        calls = 0
        def embed(self, texts):
            self.calls += 1
            return [[value * self.calls for value in vector] for vector in super().embed(texts)]
    report = run(Scaling())
    assert report["status"] == "passed" and report["retrieval_stable"]
    assert report["embedding_vectors_identical"] is False and report["embedding_changed_inputs"] == 3
    assert all(sample["cosine_to_first"] == 1. for item in report["vector_fingerprints"] for sample in item["samples"])


def test_singleton_and_batch_request_difference_is_detected():
    class ShapeDependent(Embedder):
        def embed(self, texts):
            if len(texts) == 1 and texts[0] == case().query:
                return [[0., 1., 0.]]
            return super().embed(texts)
    report = run(ShapeDependent(), single_probe_ids=["positive"])
    assert report["status"] == "failed" and not report["retrieval_stable"]
    assert report["embedding_vectors_identical"]
    assert report["batch_singleton_changed_case_ids"] == ["positive"]


def test_embedding_failure_stops_cloud_retries_and_cannot_pass():
    class Unavailable(Embedder):
        calls = 0
        def embed(self, texts):
            self.calls += 1
            raise RuntimeError("private-provider-error-and-key")
    embedder = Unavailable()
    report = run(embedder)
    assert report["status"] == "failed" and report["repeats_evaluated"] == 0
    assert report["retrieval_stable"] is False and report["embedding_vectors_identical"] is False
    assert report["runs"][0]["stage"] == "embedding_failed" and embedder.calls == 1
    assert "private-provider-error" not in json.dumps(report)


def test_singleton_provider_failure_also_stops_paid_repeats():
    class ProbeUnavailable(Embedder):
        calls = 0
        def embed(self, texts):
            self.calls += 1
            if len(texts) == 1:
                raise RuntimeError("private-singleton-provider-error")
            return super().embed(texts)
    embedder = ProbeUnavailable()
    report = run(embedder, single_probe_ids=["positive"])
    assert report["status"] == "failed" and embedder.calls == 2
    assert report["repeats_evaluated"] == 0 and report["runs"][0]["stage"] == "embedding_failed"
    assert report["cloud_embedding_requests"] == 2
    assert "private-singleton-provider-error" not in json.dumps(report)


def test_unreproducible_local_replay_fails(monkeypatch):
    evaluate = stability.evaluate_preview
    calls = 0
    def changed(*args, **kwargs):
        nonlocal calls
        calls += 1
        report = evaluate(*args, **kwargs)
        if calls == 2:
            report["results"][0]["retrieved_document_ids"] = []
        return report
    monkeypatch.setattr(stability, "evaluate_preview", changed)
    report = run()
    assert report["status"] == "failed" and report["runs"][0]["same_index_replay_stable"] is False


def test_label_failure_is_not_confused_with_instability():
    report = stability.run_stability(corpus(), [case(expected_document_ids=[], expect_empty=True)], [],
                                     Embedder(), 3, 3, .55)
    assert report["retrieval_stable"] and report["embedding_vectors_identical"]
    assert report["status"] == "failed" and report["failed_case_ids"] == ["positive"]


@pytest.mark.parametrize("overrides", [
    {"case_id": "positive", "query": "不同问题"},
    {"case_id": "other", "query": "固定公开问题，仅用于离线测试！"},
])
def test_challenge_cannot_reuse_reference_id_or_question(overrides):
    with pytest.raises(ValueError):
        stability.check_case_separation(cases(), [case(**overrides)])


@pytest.mark.parametrize("options", [
    {"repeats": 1}, {"repeats": 6}, {"top_k": 6}, {"min_score": float("nan")},
    {"single_probe_ids": ["unknown"]},
])
def test_invalid_options_fail_before_embedding(options):
    class NoNetwork(Embedder):
        def embed(self, texts):
            pytest.fail("不得调用向量服务")
    with pytest.raises(ValueError):
        run(NoNetwork(), **options)


def test_challenge_bundle_is_separate_and_structurally_consistent():
    challenge, regression = load_cases(CHALLENGE), load_cases(REGRESSION)
    assert len(challenge) == 30 and sum(case.expect_empty for case in challenge) == 15
    stability.check_case_separation(challenge, regression)
    validate_preview_inputs(load_candidates(CANDIDATES), challenge + regression)


def test_offline_check_never_opens_provider_or_index(monkeypatch, capsys):
    monkeypatch.setattr(stability, "OpenAIEmbeddings", lambda: pytest.fail("不能调用服务"))
    monkeypatch.setattr(stability, "CandidatePreviewStore", lambda *_: pytest.fail("不能打开索引"))
    assert stability.main([str(CANDIDATES), str(CHALLENGE), "--regression-cases", str(REGRESSION),
                           "--single-probe-case-id", "unsupported-topic-content", "--check"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["embedding_called"] is False and result["index_opened"] is False
    assert result["estimated_cloud_requests"] == 15 and result["estimated_embedded_texts"] == 159


def test_report_saved_with_input_hashes_even_when_labels_fail(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(stability, "OpenAIEmbeddings", Embedder)
    monkeypatch.setattr(stability, "check_configuration", lambda: [])
    output = tmp_path / "stability.json"
    assert stability.main([str(CANDIDATES), str(CHALLENGE), "--output", str(output)]) == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["candidate_sha256"]) == len(report["cases_sha256"]) == 64
    assert report["retrieval_stable"] and report["status"] == "failed"
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


@pytest.mark.parametrize("output", [".env", "docs/knowledge.candidates.json", "docs/knowledge-evaluation.challenge.json",
                                         "docs/knowledge-evaluation.draft.json"])
def test_report_cannot_overwrite_sources_or_secrets(output, monkeypatch):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(stability, "OpenAIEmbeddings", lambda: pytest.fail("不能调用服务"))
    with pytest.raises(ValueError):
        stability.main([str(CANDIDATES), str(CHALLENGE), "--regression-cases", str(REGRESSION), "--output", output])


def test_store_closed_on_invalid_index_ingestion(monkeypatch):
    instances = []
    class FailingStore:
        def __init__(self, *_):
            self.closed = False
            instances.append(self)
        def ingest(self, *_):
            raise RuntimeError("private-index-error")
        def close(self):
            self.closed = True
    monkeypatch.setattr(stability, "CandidatePreviewStore", FailingStore)
    report = run()
    assert report["status"] == "failed" and instances and all(item.closed for item in instances)
    assert "private-index-error" not in json.dumps(report)
