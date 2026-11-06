"""重复检查公共草稿的向量和检索稳定性；不读宝宝库，不打开正式Qdrant。"""

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import struct
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.schemas.advisor import advisor_today
from app.services.knowledge import OpenAIEmbeddings, validate_embedding_vectors
from scripts.check_candidates import load_candidates
from scripts.check_knowledge import check_configuration
from scripts.evaluate_knowledge import load_cases
from scripts.preview_candidates import CandidatePreviewStore, evaluate_preview, validate_preview_inputs


BATCH_SIZE = 16


class SingletonEmbeddingFailure(Exception):
    """用于停止付费重复的内部标记，不携带服务原始异常。"""


def normalized_query(query):
    return "".join(char.casefold() for char in unicodedata.normalize("NFKC", query)
                   if char.isalnum())


def check_case_separation(cases, regression_cases):
    if {item.case_id for item in cases} & {item.case_id for item in regression_cases}:
        raise ValueError("挑战集与回归集不能重复case_id")
    if {normalized_query(item.query) for item in cases} & {
        normalized_query(item.query) for item in regression_cases
    }:
        raise ValueError("挑战集不能直接重复回归问题")


def prepare_inputs(candidates, cases):
    """只保留本次公开语料，标记用例ID而非将问题写进报告。"""
    inputs = {}
    for item in candidates:
        for index, part in enumerate(part.strip() for part in item.content.split("\n\n") if part.strip()):
            text = f"{item.title}\n{part}"
            inputs.setdefault(text, {"kind": "document", "ids": []})["ids"].append(f"{item.document_id}:{index}")
    for case in cases:
        inputs.setdefault(case.query, {"kind": "query", "ids": []})["ids"].append(case.case_id)
    if not 1 <= len(inputs) <= 200:
        raise ValueError("单次稳定性检查最多200段去重文本")
    return inputs


def vector_sha256(vector):
    return hashlib.sha256(b"".join(struct.pack("!d", float(value)) for value in vector)).hexdigest()


def vector_difference(first, other):
    first_norm, other_norm = math.hypot(*first), math.hypot(*other)
    left = [value / first_norm for value in first]
    right = [value / other_norm for value in other]
    cosine = max(-1., min(1., math.fsum(a * b for a, b in zip(left, right))))
    return cosine, max(abs(a - b) for a, b in zip(left, right))


class FrozenEmbeddings:
    """用本轮已校验向量重放检索；绝不在检索阶段请求外部服务。"""

    def __init__(self, dimensions, vectors):
        self.dimensions, self.vectors = dimensions, vectors

    def embed(self, texts):
        return [list(self.vectors[text]) for text in texts]


def retrieval_signature(report):
    return [(item["case_id"], item["passed"], item["retrieval_failed"],
             item["retrieved_document_ids"]) for item in report["results"]]


def evaluate_frozen(candidates, cases, vectors, dimensions, top_k, min_score):
    frozen = FrozenEmbeddings(dimensions, vectors)
    store = CandidatePreviewStore(frozen)
    try:
        store.ingest(candidates)
        report = evaluate_preview(store, cases, top_k, min_score)
        replay = evaluate_preview(store, cases, top_k, min_score)
        # 另取未过阈值前的候选，方便解释“接近但未命中”，不再联网。
        for result, case in zip(report["results"], cases):
            candidates_before_cutoff = store.search(case.query, case.age_months, case.topic,
                                                    case.as_of, top_k=top_k, min_score=0.)
            result["candidates_before_cutoff"] = candidates_before_cutoff
            result["near_cutoff_document_ids"] = [
                hit["document_id"] for hit in candidates_before_cutoff
                if abs(hit["score"] - min_score) <= .01
            ]
        # 即使两次都“无结果”，检索异常也不能视为可重现。
        same_index_stable = (report["retrieval_errors"] == replay["retrieval_errors"] == 0
                             and retrieval_signature(report) == retrieval_signature(replay)
                             and [item["retrieved_document_scores"] for item in report["results"]]
                             == [item["retrieved_document_scores"] for item in replay["results"]])
    finally:
        store.close()
    rebuilt = CandidatePreviewStore(frozen)
    try:
        rebuilt.ingest(candidates)
        rebuilt_report = evaluate_preview(rebuilt, cases, top_k, min_score)
        rebuilt_stable = (report["retrieval_errors"] == rebuilt_report["retrieval_errors"] == 0
                          and retrieval_signature(report) == retrieval_signature(rebuilt_report)
                          and [item["retrieved_document_scores"] for item in report["results"]]
                          == [item["retrieved_document_scores"] for item in rebuilt_report["results"]])
    finally:
        rebuilt.close()
    return report, same_index_stable, rebuilt_stable


def run_stability(candidates, cases, regression_cases, embedder, repeats, top_k, min_score, single_probe_ids=()):
    if not 2 <= repeats <= 5 or not 1 <= top_k <= 5 or not math.isfinite(min_score) or not 0 <= min_score <= 1:
        raise ValueError("重复次数或检索参数无效")
    check_case_separation(cases, regression_cases)
    all_cases = cases + regression_cases
    case_by_id = {case.case_id: case for case in all_cases}
    if len(set(single_probe_ids)) > 5 or not set(single_probe_ids) <= case_by_id.keys():
        raise ValueError("单条请求对照最多5例，且必须来自评估集")
    validate_preview_inputs(candidates, all_cases)
    if not cases or len(all_cases) > 100:
        raise ValueError("须有挑战问题，合计最多100例")
    inputs = prepare_inputs(candidates, all_cases)
    texts, samples, reference_vectors = list(inputs), {}, {}
    runs, cloud_requests, embedded_texts = [], 0, 0
    for repeat in range(1, repeats + 1):
        current = {}
        try:
            for offset in range(0, len(texts), BATCH_SIZE):
                batch = texts[offset:offset + BATCH_SIZE]
                cloud_requests += 1
                embedded_texts += len(batch)
                vectors = embedder.embed(batch)
                validate_embedding_vectors(vectors, len(batch), embedder.dimensions)
                current.update((text, list(vector)) for text, vector in zip(batch, vectors))
        except Exception:
            # 向量源失败时停止后续付费重试；不可记作正确拒答。
            runs.append({"repeat": repeat, "status": "failed", "stage": "embedding_failed"})
            break
        for text, vector in current.items():
            reference_vectors.setdefault(text, list(vector))
            samples.setdefault(text, []).append((repeat, vector_sha256(vector),
                                                 *vector_difference(reference_vectors[text], vector)))
        try:
            report, same_index, rebuilt = evaluate_frozen(candidates, all_cases, current,
                                                         embedder.dimensions, top_k, min_score)
            probes = []
            for case_id in dict.fromkeys(single_probe_ids):
                case = case_by_id[case_id]
                cloud_requests += 1
                embedded_texts += 1
                try:
                    probe_vectors = embedder.embed([case.query])
                    validate_embedding_vectors(probe_vectors, 1, embedder.dimensions)
                except Exception:
                    raise SingletonEmbeddingFailure() from None
                vector = probe_vectors[0]
                cosine, delta = vector_difference(current[case.query], vector)
                probe_store = CandidatePreviewStore(FrozenEmbeddings(embedder.dimensions,
                                                                    {**current, case.query: vector}))
                try:
                    probe_store.ingest(candidates)
                    probe_report = evaluate_preview(probe_store, [case], top_k, min_score)
                    probe_result = probe_report["results"][0]
                    before_cutoff = probe_store.search(case.query, case.age_months, case.topic,
                                                       case.as_of, top_k=top_k, min_score=0.)
                finally:
                    probe_store.close()
                batch_result = next(item for item in report["results"] if item["case_id"] == case_id)
                probes.append({"case_id": case_id, "vector_sha256": vector_sha256(vector),
                               "cosine_to_batch": round(cosine, 10),
                               "max_normalized_component_delta": round(delta, 10),
                               "matches_batch_retrieval": (
                                   not probe_result["retrieval_failed"] and not batch_result["retrieval_failed"]
                                   and probe_result["retrieved_document_ids"] == batch_result["retrieved_document_ids"]),
                               "evaluation": probe_result, "candidates_before_cutoff": before_cutoff})
            runs.append({"repeat": repeat, "status": report["status"], "stage": "evaluated",
                         "same_index_replay_stable": same_index, "rebuilt_index_replay_stable": rebuilt,
                         "singleton_probes": probes,
                         "evaluation": report})
        except SingletonEmbeddingFailure:
            runs.append({"repeat": repeat, "status": "failed", "stage": "embedding_failed"})
            current.clear()
            break
        except Exception:
            runs.append({"repeat": repeat, "status": "failed", "stage": "replay_or_singleton_probe_failed"})
        current.clear()
    fingerprints = [{**inputs[text], "samples": [
        {"repeat": repeat, "vector_sha256": digest, "cosine_to_first": round(cosine, 10),
         "max_normalized_component_delta": round(delta, 10)}
        for repeat, digest, cosine, delta in observations],
        "identical": len({sample[1] for sample in observations}) == 1}
        for text, observations in samples.items()]
    evaluations = [item for item in runs if item["stage"] == "evaluated"]
    complete = len(evaluations) == repeats
    changed_case_ids = []
    if evaluations:
        first = evaluations[0]["evaluation"]["results"]
        changed_case_ids = [item["case_id"] for index, item in enumerate(first) if any(
            retrieval_signature(run["evaluation"])[index] != retrieval_signature(evaluations[0]["evaluation"])[index]
            for run in evaluations[1:]
        )]
    shape_changed_cases = sorted({probe["case_id"] for run in evaluations
                                 for probe in run["singleton_probes"] if not probe["matches_batch_retrieval"]})
    stable = (complete and not changed_case_ids and not shape_changed_cases and all(
        run["same_index_replay_stable"] and run["rebuilt_index_replay_stable"] for run in evaluations
    ))
    passed = stable and all(run["status"] == "passed" for run in runs)
    failed_case_ids = sorted({item["case_id"] for run in evaluations
                              for item in run["evaluation"]["results"] if not item["passed"]})
    report = {
        "schema_version": "candidate-stability-v1", "status": "passed" if passed else "failed",
        "evaluated_on": advisor_today().isoformat(), "evaluation_scope": "pending_candidate_stability_only",
        "challenge_cases": len(cases), "regression_cases": len(regression_cases),
        "repeats_requested": repeats, "repeats_evaluated": len(evaluations),
        "retrieval_stable": stable, "changed_case_ids": changed_case_ids,
        "batch_singleton_changed_case_ids": shape_changed_cases,
        "failed_case_ids": failed_case_ids,
        "embedding_vectors_identical": complete and all(item["identical"] for item in fingerprints),
        "embedding_changed_inputs": sum(not item["identical"] for item in fingerprints),
        "embedding_model": embedder.model, "embedding_dimensions": embedder.dimensions,
        "cloud_embedding_requests": cloud_requests, "cloud_embedded_texts": embedded_texts,
        "unique_input_texts": len(texts), "embedding_batch_size": BATCH_SIZE,
        "top_k": top_k, "min_score": min_score, "vector_fingerprints": fingerprints, "runs": runs,
        "index_storage": "memory", "production_index_opened": False,
        "application_rag_modified": False, "candidate_review_status": "pending",
        "limitations": ["synthetic_labels_not_independently_reviewed", "no_content_approval",
                        "batched_embedding_not_identical_to_live_request_pattern",
                        "finite_repeats_cannot_establish_provider_determinism",
                        "candidate_retrieval_not_final_answer_evaluation"],
    }
    reference_vectors.clear()
    return report


def main(argv=None):
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--regression-cases", type=Path)
    parser.add_argument("--repeats", type=int, choices=range(2, 6), default=3)
    parser.add_argument("--single-probe-case-id", action="append", default=[],
                        help="另用单条Embedding请求对照指定用例，最多5例")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    paths = [args.candidates, args.cases] + ([args.regression_cases] if args.regression_cases else [])
    if args.output and (args.output.suffix.lower() != ".json" or args.output.resolve() in {
        path.resolve() for path in paths
    }):
        raise ValueError("报告须另存JSON，不能覆盖输入")
    candidates, cases = load_candidates(args.candidates), load_cases(args.cases)
    regression = load_cases(args.regression_cases) if args.regression_cases else []
    check_case_separation(cases, regression)
    validate_preview_inputs(candidates, cases + regression)
    if len(set(args.single_probe_case_id)) > 5 or not set(args.single_probe_case_id) <= {
        case.case_id for case in cases + regression
    }:
        raise ValueError("单条请求对照用例无效")
    if len(cases + regression) > 100:
        raise ValueError("用例合计最多100条")
    inputs = prepare_inputs(candidates, cases + regression)
    if args.check:
        print(json.dumps({"status": "valid", "challenge_cases": len(cases),
                          "regression_cases": len(regression), "unique_input_texts": len(inputs),
                          "estimated_cloud_requests": args.repeats * (
                              math.ceil(len(inputs) / BATCH_SIZE) + len(set(args.single_probe_case_id))),
                          "estimated_embedded_texts": args.repeats * (len(inputs) + len(set(args.single_probe_case_id))),
                          "repeats": args.repeats, "embedding_called": False, "index_opened": False}))
        return 0
    if check_configuration():
        print(json.dumps({"status": "embedding_configuration_incomplete"}))
        return 1
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in zip(["candidate_sha256", "cases_sha256", "regression_cases_sha256"], paths)}
    report = run_stability(candidates, cases, regression, OpenAIEmbeddings(), args.repeats,
                           settings.RAG_TOP_K, settings.RAG_MIN_SCORE, args.single_probe_case_id)
    report.update(hashes)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "challenge_cases", "regression_cases", "repeats_evaluated", "retrieval_stable",
        "embedding_vectors_identical", "embedding_changed_inputs", "changed_case_ids", "failed_case_ids",
        "batch_singleton_changed_case_ids",
        "cloud_embedding_requests", "cloud_embedded_texts", "production_index_opened",
    )}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"status": "stability_configuration_or_validation_error"}))
        raise SystemExit(1)
