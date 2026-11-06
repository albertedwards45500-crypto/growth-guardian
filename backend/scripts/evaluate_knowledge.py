"""按公开测试问题评估知识检索，不调用问答模型、不读取宝宝库、不写索引。"""

import argparse
from datetime import date
import json
import logging
from pathlib import Path
import sys
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import Field, model_validator

from app.core.config import settings
from app.schemas.advisor import AdvisorSchema, advisor_today
from app.services.knowledge import get_knowledge_store
from scripts.check_knowledge import check_configuration


class EvaluationCase(AdvisorSchema):
    case_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    query: str = Field(min_length=2, max_length=500)
    age_months: int = Field(ge=0, le=36)
    topic: Literal["growth_review", "diet_review", "recipe_recommendation", "feeding_knowledge"]
    as_of: date
    expected_document_ids: list[str] = Field(default_factory=list, max_length=20)
    forbidden_document_ids: list[str] = Field(default_factory=list, max_length=20)
    expect_empty: bool = False

    @model_validator(mode="after")
    def valid_expectations(self):
        if len(self.query.strip()) < 2 or self.as_of > advisor_today():
            raise ValueError("问题或查询日期无效")
        expected, forbidden = set(self.expected_document_ids), set(self.forbidden_document_ids)
        if bool(expected) == self.expect_empty or expected & forbidden:
            raise ValueError("必须指定相关文献或预期无结果，且正负标签不能冲突")
        if any(not item.strip() for item in expected | forbidden):
            raise ValueError("文献标签不能为空")
        if len(expected) != len(self.expected_document_ids) or len(forbidden) != len(self.forbidden_document_ids):
            raise ValueError("文献标签不能重复")
        return self


def load_cases(path: Path) -> list[EvaluationCase]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise ValueError("评估文件须包含1至100条公开测试问题")
    cases = [EvaluationCase.model_validate(item) for item in raw]
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("case_id不能重复")
    return cases


def evaluate_cases(store, cases: list[EvaluationCase], top_k: int, min_score: float) -> dict:
    """文献级标签：重复命中文献只计一次；不将相似度解释为正确率。"""
    results, recalls, precisions, reciprocal_ranks = [], [], [], []
    positive_hits = empty_passes = errors = 0
    for case in cases:
        failed = False
        try:
            hits = store.search(case.query, case.age_months, case.topic, case.as_of,
                                top_k=top_k, min_score=min_score)
            retrieved = list(dict.fromkeys(hit["document_id"] for hit in hits))
        except Exception:
            retrieved, failed = [], True
            errors += 1
        relevant = set(case.expected_document_ids)
        matched = relevant & set(retrieved)
        forbidden = set(case.forbidden_document_ids) & set(retrieved)
        passed = not failed and not forbidden and (not retrieved if case.expect_empty else relevant <= set(retrieved))
        if relevant:
            positive_hits += int(bool(matched))
            recalls.append(len(matched) / len(relevant))
            precisions.append(len(matched) / len(retrieved) if retrieved else 0)
            reciprocal_ranks.append(next((1 / rank for rank, item in enumerate(retrieved, 1) if item in relevant), 0))
        elif passed:
            empty_passes += 1
        results.append({"case_id": case.case_id, "passed": passed, "retrieved_document_ids": retrieved,
                        "missing_document_ids": sorted(relevant - set(retrieved)),
                        "forbidden_document_ids": sorted(forbidden), "retrieval_failed": failed})
    def mean(items):
        return round(sum(items) / len(items), 4) if items else None
    empty_count = sum(case.expect_empty for case in cases)
    return {
        "status": "passed" if all(item["passed"] for item in results) else "failed",
        "top_k": top_k, "min_score": min_score, "cases": len(cases), "positive_cases": len(recalls),
        "empty_cases": empty_count, "retrieval_errors": errors,
        "hit_rate": round(positive_hits / len(recalls), 4) if recalls else None,
        "mean_recall": mean(recalls), "mean_precision": mean(precisions), "mrr": mean(reciprocal_ranks),
        "empty_result_accuracy": round(empty_passes / empty_count, 4) if empty_count else None,
        "results": results,
    }


def main(argv=None) -> int:
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--check", action="store_true", help="只校验评估文件，不调用服务或打开索引")
    args = parser.parse_args(argv)
    cases = load_cases(args.file)
    if args.check:
        print(json.dumps({"status": "valid", "cases": len(cases), "embedding_called": False, "index_opened": False}))
        return 0
    if check_configuration():
        print(json.dumps({"status": "embedding_configuration_incomplete"}))
        return 1
    store = get_knowledge_store()
    try:
        report = evaluate_cases(store, cases, settings.RAG_TOP_K, settings.RAG_MIN_SCORE)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["status"] == "passed" else 1
    finally:
        store.client.close()
        get_knowledge_store.cache_clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"status": "evaluation_configuration_or_validation_error"}))
        raise SystemExit(1)
