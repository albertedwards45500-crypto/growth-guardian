"""仅在内存Qdrant中评估待审核资料；不会打开正式索引或启用应用RAG。"""

import argparse
import hashlib
import json
import logging
import math
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.schemas.advisor import advisor_today
from app.schemas.knowledge_candidate import KnowledgeCandidate
from app.services.knowledge import OpenAIEmbeddings, validate_embedding_vectors
from app.services.knowledge_retrieval import STRATEGIES, retrieve_candidates
from scripts.check_candidates import load_candidates
from scripts.check_knowledge import check_configuration
from scripts.evaluate_knowledge import evaluate_cases, load_cases


def validate_preview_inputs(candidates, cases):
    """先核对全部来源和标签；来源核对声明不代表医学内容审核。"""
    documents = {item.document_id: item for item in candidates}
    if not documents or len(documents) != len(candidates):
        raise ValueError("预览资料不能为空或重复")
    if any(item.source_checked_on is None or not item.source_excerpt for item in candidates):
        raise ValueError("预览前须核对公开来源并记录日期和原文定位")
    for case in cases:
        labels = set(case.expected_document_ids) | set(case.forbidden_document_ids)
        if not labels <= documents.keys():
            raise ValueError("评估标签引用了资料包之外的文献")
        for document_id in case.expected_document_ids:
            item = documents[document_id]
            if (case.topic not in item.topics
                    or not item.age_min_months <= case.age_months <= item.age_max_months
                    or max(item.drafted_on, item.source_checked_on) > case.as_of):
                raise ValueError("正例标签与预览的月龄、主题或日期范围冲突")


class CandidatePreviewStore:
    """独立的离线评估适配器；保持pending，不复用正式导入契约。"""

    collection = "pending_knowledge_preview"

    def __init__(self, embedder, *, strategy="baseline"):
        if strategy not in STRATEGIES:
            raise ValueError("候选召回策略无效")
        # 固定内存模式，不接受路径、远端地址或应用集合配置。
        self.client = QdrantClient(location=":memory:")
        self.embedder = embedder
        self.strategy = strategy
        self.embedding_requests = 0
        self.embedded_texts = 0
        self._query_vectors = {}
        self._chunks = {}

    def _embed(self, texts):
        self.embedding_requests += 1
        self.embedded_texts += len(texts)
        vectors = self.embedder.embed(texts)
        validate_embedding_vectors(vectors, len(texts), self.embedder.dimensions)
        return vectors

    def ingest(self, candidates):
        candidates = [KnowledgeCandidate.model_validate(item.model_dump()) for item in candidates]
        validate_preview_inputs(candidates, [])
        chunks = [(item, part.strip()) for item in candidates
                  for part in item.content.split("\n\n") if part.strip()]
        if len(chunks) > 200:
            raise ValueError("单次预览最多200个段落")
        vectors = self._embed([f"{item.title}\n{text}" for item, text in chunks])
        self._chunks = {
            str(uuid5(NAMESPACE_URL, f"candidate-preview:{item.document_id}:{index}")): {
                "id": f"candidate:{uuid5(NAMESPACE_URL, f'candidate-preview:{item.document_id}:{index}')}",
                "document_id": item.document_id, "text": text, "title": item.title,
                "url": str(item.source_url), "version": item.version,
            } for index, (item, text) in enumerate(chunks)
        }
        self.client.create_collection(self.collection, vectors_config=models.VectorParams(
            size=self.embedder.dimensions, distance=models.Distance.COSINE,
        ))
        self.client.upsert(self.collection, points=[
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"candidate-preview:{item.document_id}:{index}")),
                vector=vector,
                payload={"document_id": item.document_id, "review_status": "pending",
                         "scope": item.scope, "topics": item.topics,
                         "age_min_months": item.age_min_months, "age_max_months": item.age_max_months,
                         "available_ordinal": max(item.drafted_on, item.source_checked_on).toordinal()},
            ) for index, ((item, _), vector) in enumerate(zip(chunks, vectors))
        ], wait=True)
        return len(chunks)

    def search(self, query, age_months, topic, as_of, top_k=3, min_score=.55):
        return [{"document_id": hit["document_id"], "score": hit["score"]}
                for hit in self.search_chunks(query, age_months, topic, as_of, top_k, min_score)]

    def search_chunks(self, query, age_months, topic, as_of, top_k=3, min_score=.55):
        """仅隔离全链路自检使用；返回原段落，仍然不生成审核元数据。"""
        if not query.strip() or len(query) > 500 or not 1 <= top_k <= 5 or not 0 <= min_score <= 1:
            raise ValueError("预览检索参数无效")
        if query not in self._query_vectors:
            self._query_vectors[query] = self._embed([query])[0]
        metadata_filter = models.Filter(must=[
                models.FieldCondition(key="review_status", match=models.MatchValue(value="pending")),
                models.FieldCondition(key="scope", match=models.MatchValue(value="general_education")),
                models.FieldCondition(key="topics", match=models.MatchValue(value=topic)),
                models.FieldCondition(key="age_min_months", range=models.Range(lte=age_months)),
                models.FieldCondition(key="age_max_months", range=models.Range(gte=age_months)),
                models.FieldCondition(key="available_ordinal", range=models.Range(lte=as_of.toordinal())),
            ])

        def dense(limit, threshold):
            result = self.client.query_points(
                self.collection, query=self._query_vectors[query], limit=limit,
                score_threshold=threshold, with_vectors=False, query_filter=metadata_filter,
            )
            return [{**self._chunks[str(point.id)], "score": round(point.score, 5)} for point in result.points]

        def lexical(limit):
            points, next_page = self.client.scroll(self.collection, scroll_filter=metadata_filter,
                                                   limit=limit, with_payload=True, with_vectors=False)
            if next_page is not None:
                raise ValueError("预览字面召回超过有界扫描上限")
            return [{**self._chunks[str(point.id)], "score": None} for point in points]

        return retrieve_candidates(
            query, dense, lexical, strategy=self.strategy, top_k=top_k, min_score=min_score,
            candidate_top_k=settings.RAG_CANDIDATE_TOP_K,
            candidate_min_score=settings.RAG_CANDIDATE_MIN_SCORE,
            lexical_scan_limit=settings.RAG_LEXICAL_SCAN_LIMIT,
        )

    def close(self):
        self._query_vectors.clear()
        self._chunks.clear()
        self.client.close()


def evaluate_preview(store, cases, top_k, min_score):
    """给候选报告补充逐例得分；失败时不沿用上一例的诊断数据。"""
    class DiagnosticStore:
        def __init__(self):
            self.scores = []

        def search(self, *args, **kwargs):
            self.scores.append([])
            hits = store.search(*args, **kwargs)
            self.scores[-1] = hits
            return hits

    diagnostic = DiagnosticStore()
    report = evaluate_cases(diagnostic, cases, top_k, min_score)
    for result, scores in zip(report["results"], diagnostic.scores):
        result["retrieved_document_scores"] = scores
    return report


def main(argv=None):
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--check", action="store_true", help="只检查来源元数据与标签，不发网络请求")
    parser.add_argument("--output", type=Path, help="保存不含正文、问题或密钥的JSON报告")
    parser.add_argument("--compare-thresholds", nargs="+", type=float, default=[],
                        help="对比最多10个阈值；同次运行复用查询向量，不修改应用配置")
    args = parser.parse_args(argv)
    if len(args.compare_thresholds) > 10 or any(
        not math.isfinite(value) or not 0 <= value <= 1 for value in args.compare_thresholds
    ):
        raise ValueError("比较阈值须为0至1，最多10个")
    if args.output and (args.output.suffix.lower() != ".json" or args.output.resolve() in {
        args.candidates.resolve(), args.cases.resolve(),
    }):
        raise ValueError("报告必须另存为JSON，不能覆盖输入资料")
    candidates, cases = load_candidates(args.candidates), load_cases(args.cases)
    validate_preview_inputs(candidates, cases)
    if args.check:
        print(json.dumps({"status": "valid", "documents": len(candidates), "cases": len(cases),
                          "embedding_called": False, "index_opened": False}))
        return 0
    if check_configuration():
        print(json.dumps({"status": "embedding_configuration_incomplete"}))
        return 1
    embedder = OpenAIEmbeddings()
    store = CandidatePreviewStore(embedder)
    try:
        chunks = store.ingest(candidates)
        report = evaluate_preview(store, cases, settings.RAG_TOP_K, settings.RAG_MIN_SCORE)
        comparisons = [evaluate_preview(store, cases, settings.RAG_TOP_K, threshold)
                       for threshold in dict.fromkeys(args.compare_thresholds)]
        report.update(
            schema_version="candidate-preview-v1", evaluated_on=advisor_today().isoformat(),
            evaluation_scope="pending_candidate_retrieval_only",
            candidate_review_status="pending", production_index_opened=False,
            threshold_comparison=comparisons,
            index_storage="memory", application_rag_modified=False,
            documents=len(candidates), chunks=chunks,
            embedding_model=embedder.model, embedding_dimensions=embedder.dimensions,
            embedding_requests=store.embedding_requests, embedded_texts=store.embedded_texts,
            candidate_sha256=hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
            cases_sha256=hashlib.sha256(args.cases.read_bytes()).hexdigest(),
            limitations=["draft_labels_not_independently_reviewed", "no_content_approval",
                         "no_production_review_or_expiry_filter_evaluation",
                         "no_chat_model_or_baby_data_evaluation"],
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
            summary_fields = ("status", "min_score", "cases", "retrieval_errors", "mean_recall",
                              "mean_precision", "empty_result_accuracy")
            print(json.dumps({
                "evaluation_scope": report["evaluation_scope"],
                "baseline": {key: report[key] for key in summary_fields},
                "threshold_comparison": [{key: item[key] for key in summary_fields} for item in comparisons],
                "embedding_requests": store.embedding_requests, "embedded_texts": store.embedded_texts,
                "production_index_opened": False, "report_saved": True,
            }))
        else:
            print(rendered)
        return 0 if report["status"] == "passed" else 1
    finally:
        store.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"status": "candidate_preview_configuration_or_validation_error"}))
        raise SystemExit(1)
