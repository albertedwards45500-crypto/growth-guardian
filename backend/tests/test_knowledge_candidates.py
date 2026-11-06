"""待审核资料的隔离测试：可校验、不可直接导入。"""

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.advisor import advisor_today
from app.schemas.knowledge_candidate import KnowledgeCandidate
from scripts.check_candidates import load_candidates
from scripts.knowledge_files import load_documents


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "docs" / "knowledge.candidates.json"


def test_candidate_bundle_is_pending_and_structurally_valid():
    candidates = load_candidates(CANDIDATES)
    assert len(candidates) == 5
    assert {item.review_status for item in candidates} == {"pending"}
    assert all(item.source_url.scheme == "https" for item in candidates)
    assert all(item.source_checked_on and item.source_excerpt and item.source_section for item in candidates)
    assert {item.content_kind for item in candidates} == {"source_summary", "translation_draft"}


def test_formal_loader_rejects_pending_bundle():
    with pytest.raises(ValidationError):
        load_documents(CANDIDATES)


def test_candidate_rejects_future_draft_and_long_paragraph():
    base = {
        "document_id": "candidate-test", "title": "待审核资料", "content": "短文本",
        "source_url": "https://example.org/source", "drafted_on": advisor_today().isoformat(),
        "version": "draft", "review_status": "pending", "reviewer_notes": "待核对",
        "scope": "general_education", "topics": ["feeding_knowledge"],
        "age_min_months": 0, "age_max_months": 36,
    }
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate({**base, "drafted_on": advisor_today() + timedelta(days=1)})
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate({**base, "content": "x" * 1201})


def test_honey_draft_uses_completed_months_below_twelve():
    honey = next(item for item in load_candidates(CANDIDATES) if item.document_id == "nhs_honey_under_12_months")
    assert honey.age_min_months == 0 and honey.age_max_months == 11


@pytest.mark.parametrize("overrides", [
    {"source_checked_on": "2026-10-23", "source_excerpt": None},
    {"source_checked_on": None},
    {"source_checked_on": advisor_today() + timedelta(days=1)},
    {"source_excerpt": " "}, {"source_section": " "}, {"baby_id": 1},
])
def test_candidate_source_metadata_is_consistent(overrides):
    candidate = load_candidates(CANDIDATES)[0].model_dump()
    with pytest.raises(ValidationError):
        KnowledgeCandidate.model_validate({**candidate, **overrides})
