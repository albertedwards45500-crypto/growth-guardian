"""先用47题开发集选择候选策略，再只评一次新增验证集；不启用正式RAG。"""

import argparse
import hashlib
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.schemas.advisor import advisor_today
from app.services.knowledge import OpenAIEmbeddings
from app.services.knowledge_retrieval import STRATEGIES
from scripts.check_candidates import load_candidates
from scripts.check_rag_pipeline import ResponsesModel, run_pipeline
from scripts.check_retrieval_stability import check_case_separation
from scripts.evaluate_knowledge import load_cases
from scripts.preview_candidates import validate_preview_inputs


class CachedEmbeddings:
    """同一比较中复用相同文本向量；不落盘、不缓存业务数据。"""

    def __init__(self, delegate, guard=None):
        self.delegate = delegate
        self.model, self.dimensions, self.identity = delegate.model, delegate.dimensions, delegate.identity
        self.cache, self.cloud_requests, self.embedded_texts = {}, 0, 0
        self.guard = guard

    def embed(self, texts):
        missing = list(dict.fromkeys(text for text in texts if text not in self.cache))
        if missing:
            if self.guard:
                self.guard()
            self.cloud_requests += 1
            self.embedded_texts += len(missing)
            vectors = self.delegate.embed(missing)
            from app.services.knowledge import validate_embedding_vectors
            validate_embedding_vectors(vectors, len(missing), self.dimensions)
            self.cache.update(zip(missing, vectors))
        return [self.cache[text] for text in texts]


def summarize(report, cases):
    results = {item["case_id"]: item for item in report["results"]}
    empty = [results[case.case_id] for case in cases if case.expect_empty]
    positive = [results[case.case_id] for case in cases if not case.expect_empty]
    return {
        "cases": len(cases), "structure_passed": report["structure_passed"],
        "semantic_passed": report["semantic_passed"],
        "exact_selection_matches": report["selection_exact_matches"],
        "empty_cases": len(empty), "empty_cases_passed": sum(item["semantic_passed"] for item in empty),
        "positive_cases": len(positive), "positive_cases_passed": sum(item["semantic_passed"] for item in positive),
        "safety_checks_passed": sum(item["passed"] for item in report["checks"]),
        "safety_checks": len(report["checks"]),
        "failed_case_ids": [item["case_id"] for item in report["results"] if not item["semantic_passed"]],
    }


def choose_strategy(development):
    """仅开发集决策：安全/无资料表现不得退步，再比较命中和精确选择，平局选简单策略。"""
    baseline = development["baseline"]["summary"]
    eligible = []
    for strategy in STRATEGIES:
        metric = development[strategy]["summary"]
        if (metric["structure_passed"] == metric["cases"]
                and metric["safety_checks_passed"] == metric["safety_checks"]
                and metric["empty_cases_passed"] >= baseline["empty_cases_passed"]
                and metric["semantic_passed"] >= baseline["semantic_passed"]
                and metric["exact_selection_matches"] >= baseline["exact_selection_matches"]):
            eligible.append(strategy)
    return max(eligible, key=lambda strategy: (
        development[strategy]["summary"]["semantic_passed"],
        development[strategy]["summary"]["exact_selection_matches"],
        -STRATEGIES.index(strategy),
    )) if eligible else "baseline"


def run_comparison(candidates, development_cases, holdout_cases, embedder, model_factory=None, progress=None):
    report = {"schema_version": "rag-retrieval-comparison-v1", "evaluated_on": str(advisor_today()),
              "status": "running", "development": {}, "holdout": {},
              "selection_uses_holdout": False, "production_rag_configuration_modified": False,
              "candidate_review_status": "pending", "top_k": settings.RAG_TOP_K,
              "min_score": settings.RAG_MIN_SCORE, "candidate_top_k": settings.RAG_CANDIDATE_TOP_K,
              "candidate_min_score": settings.RAG_CANDIDATE_MIN_SCORE,
              "lexical_scan_limit": settings.RAG_LEXICAL_SCAN_LIMIT,
              "model_request_limit": 260, "cloud_model_requests": 0,
              "limitations": ["synthetic_labels_not_expert_reviewed", "one_live_run_per_strategy",
                              "same_embeddings_reused_to_control_vector_variation", "no_content_approval",
                              "holdout_is_consumed_after_this_run", "no_production_or_real_baby_data"]}

    def require_budget():
        if report["cloud_model_requests"] >= report["model_request_limit"]:
            raise RuntimeError("模型请求预算已用完，不再发起云端调用")

    shared_embeddings = CachedEmbeddings(embedder, guard=require_budget)

    def factory(scope):
        delegate = model_factory(scope) if model_factory else ResponsesModel(knowledge_scope=scope)
        class BudgetedModel:
            def respond(self, inputs, definitions):
                require_budget()
                report["cloud_model_requests"] += 1
                return delegate.respond(inputs, definitions)
        return BudgetedModel()

    try:
        for stage, cases, strategies in (("development", development_cases, STRATEGIES),
                                          ("holdout", holdout_cases, None)):
            if stage == "holdout":
                report["selected_strategy"] = choose_strategy(report["development"])
                # 决策先固定并显式报告，再读取验证结果；不据其结果重新选择。
                strategies = tuple(dict.fromkeys(("baseline", report["selected_strategy"])))
                if progress:
                    progress({"stage": "strategy_frozen", "selected_strategy": report["selected_strategy"]})
            for strategy in strategies:
                def emit(item):
                    if progress:
                        progress({"stage": stage, "strategy": strategy, **item})
                pipeline = run_pipeline(candidates, cases, shared_embeddings, model_factory=factory,
                                        progress=emit, strategy=strategy)
                metric = summarize(pipeline, cases)
                report[stage][strategy] = {"summary": metric, "pipeline": pipeline}
                if (metric["structure_passed"] != metric["cases"]
                        or metric["safety_checks_passed"] != metric["safety_checks"]):
                    report["status"] = "stopped_on_structure_or_safety_failure"
                    return report
        selected = report["holdout"][report["selected_strategy"]]["summary"]
        report["status"] = "passed" if selected["semantic_passed"] == selected["cases"] else "quality_failed"
        return report
    finally:
        report["cloud_embedding_requests"] = shared_embeddings.cloud_requests
        report["cloud_embedded_texts"] = shared_embeddings.embedded_texts
        shared_embeddings.cache.clear()


def main(argv=None):
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("development", type=Path)
    parser.add_argument("--regression-cases", type=Path, required=True)
    parser.add_argument("--holdout-cases", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    paths = [args.candidates, args.development, args.regression_cases, args.holdout_cases]
    if args.output and (args.output.suffix.lower() != ".json" or args.output.resolve() in {path.resolve() for path in paths}):
        raise ValueError("报告不能覆盖输入")
    candidates = load_candidates(args.candidates)
    development, regression = load_cases(args.development), load_cases(args.regression_cases)
    holdout = load_cases(args.holdout_cases)
    check_case_separation(development, regression)
    development += regression
    check_case_separation(development, holdout)
    validate_preview_inputs(candidates, development + holdout)
    if len(development + holdout) > 100:
        raise ValueError("总计最多100题")
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in zip(("candidates", "development", "regression", "holdout"), paths)}
    if args.check:
        print(json.dumps({"status": "valid", "development_cases": len(development), "holdout_cases": len(holdout),
                          "cloud_called": False, "input_sha256": hashes}))
        return 0
    if not all((settings.OPENAI_API_KEY.get_secret_value(), settings.ADVISOR_MODEL,
                settings.RAG_EMBEDDING_API_KEY.get_secret_value())):
        raise ValueError("模型或Embedding配置不足")
    env = Path(__file__).resolve().parents[1] / ".env"
    env_before = hashlib.sha256(env.read_bytes()).digest() if env.exists() else None
    initial = settings.RAG_ENABLED, settings.RAG_RETRIEVAL_STRATEGY
    report = run_comparison(candidates, development, holdout, OpenAIEmbeddings(),
                            progress=lambda item: print(json.dumps(item), flush=True))
    report["input_sha256"] = hashes
    report["env_file_unchanged"] = env_before == (hashlib.sha256(env.read_bytes()).digest() if env.exists() else None)
    report["settings_restored"] = initial == (settings.RAG_ENABLED, settings.RAG_RETRIEVAL_STRATEGY)
    if not report["env_file_unchanged"] or not report["settings_restored"]:
        report["status"] = "isolation_failed"
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "selected_strategy": report.get("selected_strategy"),
                      "development": {key: value["summary"] for key, value in report["development"].items()},
                      "holdout": {key: value["summary"] for key, value in report["holdout"].items()},
                      "cloud_model_requests": report["cloud_model_requests"],
                      "cloud_embedding_requests": report["cloud_embedding_requests"],
                      "env_file_unchanged": report["env_file_unchanged"], "settings_restored": report["settings_restored"]}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"status": "comparison_configuration_or_provider_error"}))
        raise SystemExit(1)
