"""开发集先选策略，验证集后读取；不联网、不使用生产数据库。"""

import json
import logging
from pathlib import Path

import pytest

from scripts import compare_retrieval as comparison
from tests.test_knowledge import FakeEmbeddings


class Embeddings(FakeEmbeddings):
    model = "offline-embedding"
    def __init__(self):
        self.calls = []
    def embed(self, texts):
        self.calls.append(list(texts))
        return super().embed(texts)


def metric(passed=47, exact=40, empty=20, structure=47, safe=9):
    return {"summary": {"cases": 47, "semantic_passed": passed, "exact_selection_matches": exact,
                        "structure_passed": structure, "empty_cases_passed": empty,
                        "safety_checks_passed": safe, "safety_checks": 9}}


def test_same_text_vectors_are_reused_without_disk_or_cross_model_state():
    delegate = Embeddings()
    cached = comparison.CachedEmbeddings(delegate)
    first = cached.embed(["公开材料", "问题", "问题"])
    assert cached.embed(["问题", "公开材料"])[0] == first[1]
    assert delegate.calls == [["公开材料", "问题"]]
    assert cached.cloud_requests == 1 and cached.embedded_texts == 2


def test_cache_never_stores_invalid_provider_response():
    delegate = Embeddings()
    delegate.embed = lambda _: []
    cached = comparison.CachedEmbeddings(delegate)
    with pytest.raises(ValueError):
        cached.embed(["问题"])
    assert cached.cache == {}


def test_exhausted_budget_blocks_new_embedding_requests():
    delegate = Embeddings()
    def guard():
        raise RuntimeError("budget")
    cached = comparison.CachedEmbeddings(delegate, guard=guard)
    with pytest.raises(RuntimeError):
        cached.embed(["问题"])
    assert delegate.calls == [] and cached.cloud_requests == 0


def test_equal_quality_selects_simplest_strategy():
    assert comparison.choose_strategy({name: metric() for name in comparison.STRATEGIES}) == "baseline"


def test_improved_recall_without_safety_regression_selects_expanded():
    assert comparison.choose_strategy({"baseline": metric(45), "expanded": metric(), "hybrid": metric()}) == "expanded"


@pytest.mark.parametrize("changed", [
    {"empty": 19}, {"safe": 8}, {"structure": 46}, {"exact": 39},
])
def test_higher_recall_cannot_override_no_data_safety_structure_or_precision(changed):
    assert comparison.choose_strategy({"baseline": metric(45), "expanded": metric(**changed),
                                       "hybrid": metric(45)}) == "baseline"


def test_new_set_cannot_change_already_frozen_choice(monkeypatch):
    events = []
    def fake_run(candidates, cases, embedder, model_factory, progress, strategy):
        stage = "development" if cases == ["development"] else "holdout"
        events.append((stage, strategy))
        passed = stage == "development" or strategy == "baseline"
        if stage == "development" and strategy == "baseline":
            passed = False
        return {"structure_passed": 1, "semantic_passed": int(passed), "selection_exact_matches": int(passed),
                "results": [{"case_id": "case", "semantic_passed": passed}], "checks": [{"passed": True}]}
    monkeypatch.setattr(comparison, "run_pipeline", fake_run)
    def summary(report, cases):
        return {"cases": 1, "structure_passed": 1, "semantic_passed": report["semantic_passed"],
                "exact_selection_matches": report["selection_exact_matches"], "empty_cases_passed": 0,
                "safety_checks_passed": 1, "safety_checks": 1}
    monkeypatch.setattr(comparison, "summarize", summary)
    report = comparison.run_comparison([], ["development"], ["holdout"], Embeddings())
    assert report["selected_strategy"] == "expanded"
    assert report["status"] == "quality_failed"  # 不因验证集失败重新挑选或改标签
    assert events == [("development", "baseline"), ("development", "expanded"), ("development", "hybrid"),
                      ("holdout", "baseline"), ("holdout", "expanded")]


def test_check_is_offline_and_inputs_are_frozen(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    previous = logging.root.manager.disable
    monkeypatch.setattr(comparison, "run_comparison", lambda *args, **kwargs: pytest.fail("不能联网"))
    try:
        assert comparison.main([str(root / "docs/knowledge.candidates.json"),
                                str(root / "docs/knowledge-evaluation.challenge.json"), "--regression-cases",
                                str(root / "docs/knowledge-evaluation.draft.json"), "--holdout-cases",
                                str(root / "docs/knowledge-evaluation.holdout.json"), "--check"]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["development_cases"] == 47 and result["holdout_cases"] == 24
        assert result["cloud_called"] is False
        assert result["input_sha256"]["holdout"] == "9e6d7b7cf0ee45e7d3b571c782f479b159f6a10dbb82f04be43da8952353c0ab"
    finally:
        logging.disable(previous)
