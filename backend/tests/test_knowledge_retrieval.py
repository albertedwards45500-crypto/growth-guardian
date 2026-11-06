"""候选池扩展和字面召回始终保留审核、日期、月龄、主题与调用预算。"""

from datetime import date, timedelta

import pytest
from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.schemas.advisor import advisor_today
from app.services.knowledge import KnowledgeStore
from app.services.knowledge_retrieval import (
    lexical_rank, lexical_terms, requires_specific_fact, retrieve_candidates,
)
from scripts.check_candidates import load_candidates
from scripts.evaluate_knowledge import load_cases
from scripts.preview_candidates import CandidatePreviewStore, validate_preview_inputs
from tests.test_knowledge import FakeEmbeddings, document


def hit(key, text="引用编号", score=.5):
    return {"id": key, "title": "软件测试", "text": text, "score": score}


def test_baseline_does_not_read_lexical_or_expand_threshold():
    calls = []
    def dense(limit, threshold):
        calls.append((limit, threshold))
        return [hit("a")]
    assert retrieve_candidates("编号", dense, lambda _: pytest.fail("基线不读字面库"),
                               candidate_top_k=1) == [hit("a")]
    assert calls == [(3, .55)]


def test_expansion_is_only_candidate_pool_and_keeps_all_bounds():
    calls = []
    retrieve_candidates("编号", lambda limit, threshold: calls.append((limit, threshold)) or [],
                        lambda _: pytest.fail("扩展不读字面库"), strategy="expanded")
    assert calls == [(5, .45)]


@pytest.mark.parametrize("kwargs", [
    {"strategy": "all"}, {"top_k": 6}, {"candidate_top_k": 6},
    {"strategy": "expanded", "candidate_top_k": 2}, {"candidate_min_score": float("nan")},
    {"min_score": float("inf")}, {"lexical_scan_limit": 1001},
])
def test_invalid_policy_never_calls_database_or_embedding(kwargs):
    def forbidden(*args):
        pytest.fail("无效策略不得访问存储")
    with pytest.raises(ValueError):
        retrieve_candidates("编号", forbidden, forbidden, **kwargs)


def test_lexical_unicode_normalization_and_deterministic_ties():
    assert lexical_terms("引用编号 ＡＢＣ １２") == lexical_terms("引用编号 abc 12")
    assert lexical_rank("引用编号", [hit("b"), hit("a"), hit("z", "其他材料")]) == [hit("a"), hit("b")]


def test_lexical_ignores_generic_context_terms():
    assert lexical_rank("婴儿粥时大米和水的准确比例", [
        hit("generic", text="婴儿辅食资料说明一般喂养问题。"),
    ]) == []
    assert requires_specific_fact("煮婴儿粥时，大米和水的准确比例是多少？")
    assert not requires_specific_fact("准备吃辅食时有哪些准备信号？")


def test_hybrid_blocks_specific_fact_without_substantive_lexical_evidence():
    hits = retrieve_candidates(
        "煮婴儿粥时，大米和水的准确比例是多少？",
        lambda *_: [hit("dense")],
        lambda _: [hit("generic", text="婴儿辅食资料说明一般喂养问题。")],
        strategy="hybrid",
    )
    assert hits == []


def test_hybrid_fuses_deduplicates_and_never_relabels_cosine_score():
    dense = [hit("dense", score=.8), hit("both", score=.5)]
    lexical = [hit("both", score=None), hit("lexical", score=None)]
    hits = retrieve_candidates("引用编号", lambda *_: dense, lambda _: lexical, strategy="hybrid")
    assert hits[0]["id"] == "both" and hits[0]["retrieval_channels"] == ["dense", "lexical"]
    assert hits[0]["score"] == .5
    assert next(item for item in hits if item["id"] == "lexical")["score"] is None
    assert len({item["id"] for item in hits}) == len(hits)


def test_hybrid_scan_excess_fails_closed_instead_of_silent_sampling():
    with pytest.raises(ValueError, match="上限"):
        retrieve_candidates("编号", lambda *_: [], lambda _: [hit(str(index)) for index in range(3)],
                            strategy="hybrid", lexical_scan_limit=2)


@pytest.fixture
def store():
    instance = KnowledgeStore(QdrantClient(location=":memory:"), FakeEmbeddings(), "hybrid_test")
    instance.ingest(document(content="核对引用编号及其对应段落的原文。"))
    yield instance
    instance.client.close()


def search(store, **overrides):
    return store.search(**{"query": "无关引用编号", "age_months": 8, "topic": "feeding_knowledge",
                           "as_of": advisor_today(), "strategy": "hybrid", **overrides})


def test_lexical_adds_real_filtered_record_even_when_dense_misses(store):
    assert search(store, strategy="baseline") == []
    hits = search(store)
    assert hits and hits[0]["retrieval_channels"] == ["lexical"]
    assert hits[0]["score"] is None
    assert hits[0]["text"] == "核对引用编号及其对应段落的原文。"


@pytest.mark.parametrize("overrides", [
    {"age_months": 5}, {"age_months": 13}, {"topic": "growth_review"},
    {"as_of": date(2026, 7, 31)},
])
def test_metadata_filters_apply_to_both_retrieval_branches(store, overrides):
    assert search(store, **overrides) == []


def test_expired_or_revoked_docs_never_enter_lexical_branch(store):
    store.client.set_payload(store.collection,
                             payload={"valid_until_ordinal": (advisor_today() - timedelta(days=1)).toordinal()},
                             points=models.Filter())
    assert search(store) == []
    store.revoke(document().document_id)
    assert search(store) == []


def test_production_scan_limit_has_no_partial_success(store, monkeypatch):
    store.ingest(document(document_id="second", content="另一个引用编号与原文的测试段落。"))
    monkeypatch.setattr(settings, "RAG_LEXICAL_SCAN_LIMIT", 1)
    with pytest.raises(ValueError, match="上限"):
        search(store)


@pytest.mark.parametrize("strategy", ["expanded", "hybrid"])
def test_preview_uses_same_policy_without_bypassing_age_or_pending(strategy):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    candidates = load_candidates(root / "docs/knowledge.candidates.json")
    item = next(item for item in candidates if item.document_id == "nhs_honey_under_12_months")
    store = CandidatePreviewStore(FakeEmbeddings(), strategy=strategy)
    try:
        store.ingest([item])
        assert store.search_chunks("蜂蜜", 8, "feeding_knowledge", advisor_today())
        assert store.search_chunks("蜂蜜", 12, "feeding_knowledge", advisor_today()) == []
        assert store.search_chunks("蜂蜜", 8, "growth_review", advisor_today()) == []
        assert item.review_status == "pending"
    finally:
        store.close()


def test_preview_hybrid_abstains_on_unsupported_exact_food_ratio():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    candidates = load_candidates(root / "docs/knowledge.candidates.json")
    store = CandidatePreviewStore(FakeEmbeddings(), strategy="hybrid")
    try:
        store.ingest(candidates)
        hits = store.search_chunks(
            "煮婴儿粥时，大米和水的准确比例是多少？", 8, "feeding_knowledge", advisor_today(),
        )
        assert hits == []
    finally:
        store.close()


def test_new_validation_set_is_valid_and_separate_without_running_retrieval():
    from pathlib import Path
    from scripts.check_retrieval_stability import check_case_separation
    root = Path(__file__).resolve().parents[1]
    holdout = load_cases(root / "docs/knowledge-evaluation.holdout.json")
    development = load_cases(root / "docs/knowledge-evaluation.challenge.json") + load_cases(root / "docs/knowledge-evaluation.draft.json")
    check_case_separation(development, holdout)
    validate_preview_inputs(load_candidates(root / "docs/knowledge.candidates.json"), holdout)
    assert len(holdout) == 24 and sum(case.expect_empty for case in holdout) == 12
