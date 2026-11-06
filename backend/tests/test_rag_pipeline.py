"""全链路自检脚本的离线回归，不调用云端或正式数据库。"""

import json
import logging
from pathlib import Path

from pydantic import SecretStr
import pytest

from app.core.config import settings
from app.schemas.advisor import AdvisorAnswer, AdvisorAskRequest
from app.services.advisor_agent import ResponsesModel, run_agent
from scripts import check_rag_pipeline as pipeline
from scripts.check_candidates import load_candidates
from scripts.evaluate_knowledge import load_cases
from scripts.preview_candidates import CandidatePreviewStore
from tests.test_advisor_agent import FakeModel
from tests.test_knowledge import FakeEmbeddings

ROOT = Path(__file__).resolve().parents[1]


class Embeddings(FakeEmbeddings):
    model = "offline-embedding"


@pytest.fixture(autouse=True)
def restore_logging():
    previous = logging.root.manager.disable
    yield
    logging.disable(previous)


def inputs():
    candidates = load_candidates(ROOT / "docs/knowledge.candidates.json")
    cases = load_cases(ROOT / "docs/knowledge-evaluation.draft.json")
    return ([item for item in candidates if item.document_id == "nhs_honey_under_12_months"],
            [item for item in cases if item.case_id == "honey-eight-months"])


def test_full_api_graph_selfcheck_is_isolated_and_faults_are_safe(monkeypatch):
    monkeypatch.setattr(settings, "ADVISOR_MODEL", "offline-model")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("offline"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr("offline"))
    candidates, cases = inputs()
    report = pipeline.run_pipeline(candidates, cases, Embeddings(), model_factory=lambda scope: FakeModel())
    assert report["status"] == "passed"
    assert report["cases"] == report["structure_passed"] == report["semantic_passed"] == 1
    assert all(item["passed"] for item in report["checks"])
    assert report["production_index_open_attempts"] == 0
    assert not report["production_database_connected"]
    assert report["candidate_review_status"] == "pending" and report["privacy_passed"]
    assert settings.RAG_ENABLED is False and settings.ADVISOR_AGENT_ENABLED is False
    serialized = json.dumps(report)
    for private in ("SYNTHETIC_PRIVATE_BABY_NAME", "SYNTHETIC_SECRET_DO_NOT_EXPOSE", "source_url", "question", "text"):
        assert f'"{private}"' not in serialized


def test_chunk_preview_preserves_exact_text_without_review_metadata():
    candidates, cases = inputs()
    store = CandidatePreviewStore(Embeddings())
    try:
        store.ingest(candidates)
        case = cases[0]
        hits = store.search_chunks(case.query, case.age_months, case.topic, case.as_of)
        assert hits[0]["text"] == candidates[0].content
        assert hits[0]["id"].startswith("candidate:")
        assert "reviewed_on" not in hits[0]
        assert store.search(case.query, case.age_months, case.topic, case.as_of) == [
            {"document_id": hits[0]["document_id"], "score": hits[0]["score"]}
        ]
    finally:
        store.close()


@pytest.mark.parametrize("mutation", ["source_type", "review_date", "review_status"])
def test_preview_cannot_silently_become_reviewed(monkeypatch, mutation):
    monkeypatch.setattr(settings, "ADVISOR_MODEL", "offline-model")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", SecretStr("offline"))
    monkeypatch.setattr(settings, "RAG_EMBEDDING_API_KEY", SecretStr("offline"))
    original_factory = pipeline.preview_tools_class

    def broken_factory(store, instances):
        class BrokenTools(original_factory(store, instances)):
            def search_reviewed_knowledge(self, query, topic):
                result = super().search_reviewed_knowledge(query, topic)
                if result.evidence:
                    if mutation == "source_type":
                        result.evidence[0].type = "reviewed_knowledge"
                    elif mutation == "review_date":
                        result.evidence[0].reviewed_on = pipeline.advisor_today()
                    else:
                        result.data["review_status"] = "approved"
                return result
        return BrokenTools

    monkeypatch.setattr(pipeline, "preview_tools_class", broken_factory)
    report = pipeline.run_pipeline(*inputs(), Embeddings(), model_factory=lambda scope: FakeModel())
    assert report["status"] == "failed"
    assert report["structure_passed"] == report["semantic_passed"] == 0


@pytest.mark.parametrize("scope", ["pending", "approved", "", None])
def test_scope_must_be_explicit_and_allowlisted(scope):
    with pytest.raises(ValueError):
        ResponsesModel(knowledge_scope=scope)
    with pytest.raises(ValueError):
        run_agent(None, None, None, knowledge_scope=scope)


def test_check_validates_all_cases_without_cloud_or_database(monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "run_pipeline", lambda *args, **kwargs: pytest.fail("不得执行链路"))
    assert pipeline.main([str(ROOT / "docs/knowledge.candidates.json"),
                          str(ROOT / "docs/knowledge-evaluation.challenge.json"), "--regression-cases",
                          str(ROOT / "docs/knowledge-evaluation.draft.json"), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["cases"] == 47


@pytest.mark.parametrize("on,age", [("2026-10-23", 8), ("2026-03-31", 1), ("2026-10-23", 0)])
def test_synthetic_month_age_matches_backend(on, age):
    from datetime import date
    from app.services.growth import compute_age

    as_of = date.fromisoformat(on)
    assert compute_age(pipeline.birth_for_age(as_of, age), as_of)[0] == age
