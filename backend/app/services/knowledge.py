"""公共审核知识的 Embedding 与 Qdrant 存储，不导入任何宝宝业务表。"""

from functools import lru_cache
import hashlib
import math
from pathlib import Path
import threading
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.schemas.advisor import advisor_today
from app.schemas.knowledge import KnowledgeDocument
from app.services.knowledge_retrieval import retrieve_candidates


class OpenAIEmbeddings:
    def __init__(self):
        self.dimensions = settings.RAG_EMBEDDING_DIMENSIONS
        self.base_url = settings.RAG_EMBEDDING_BASE_URL
        self.model = settings.RAG_EMBEDDING_MODEL
        self.send_dimensions = settings.RAG_EMBEDDING_SEND_DIMENSIONS
        self.identity = f"{self.base_url}|{self.model}|{self.dimensions}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI

        with OpenAI(api_key=settings.RAG_EMBEDDING_API_KEY.get_secret_value(),
                    base_url=self.base_url, max_retries=0,
                    timeout=settings.ADVISOR_MODEL_TIMEOUT_SECONDS) as client:
            response = client.embeddings.create(
                model=self.model, input=texts, encoding_format="float",
                **({"dimensions": self.dimensions} if self.send_dimensions else {}),
            )
        items = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in items] != list(range(len(texts))):
            raise ValueError("Embedding 返回数量或顺序无效")
        vectors = [item.embedding for item in items]
        validate_embedding_vectors(vectors, len(texts), self.dimensions)
        return vectors


def validate_embedding_vectors(vectors, count: int, dimensions: int) -> None:
    """校验服务响应，防止维度、非有限数或零向量污染索引。"""
    if len(vectors) != count or any(
        len(vector) != dimensions
        or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
        or not any(vector) for vector in vectors
    ):
        raise ValueError("Embedding 向量无效")


class KnowledgeStore:
    def __init__(self, client: QdrantClient, embedder, collection: str):
        self.client, self.embedder, self.collection = client, embedder, collection
        self.vector_name = "embedding_" + hashlib.sha256(embedder.identity.encode()).hexdigest()[:16]
        self.lock = threading.RLock()

    def _exists(self):
        return self.client.collection_exists(self.collection)

    def _check_signature(self):
        vectors = self.client.get_collection(self.collection).config.params.vectors
        if not isinstance(vectors, dict) or self.vector_name not in vectors or vectors[self.vector_name].size != self.embedder.dimensions:
            raise ValueError("索引的 Embedding 模型/维度不匹配，请使用新的集合重建")

    def _embed(self, texts):
        vectors = self.embedder.embed(texts)
        validate_embedding_vectors(vectors, len(texts), self.embedder.dimensions)
        return vectors

    def ingest(self, document: KnowledgeDocument) -> int:
        document = KnowledgeDocument.model_validate(document.model_dump())
        if document.valid_until < advisor_today():
            raise ValueError("不能导入已过期文献")
        metadata = document.model_dump(mode="json", exclude={"content"})
        revision = hashlib.sha256(document.model_dump_json().encode()).hexdigest()
        paragraphs = [part.strip() for part in document.content.split("\n\n") if part.strip()]
        with self.lock:
            if self._exists():
                self._check_signature()
            # 在任何数据库写入前先获得完整向量，网络失败不破坏已有版本。
            vectors = self._embed([f"{document.title}\n{part}" for part in paragraphs])
            if not self._exists():
                self.client.create_collection(self.collection, vectors_config={
                    self.vector_name: models.VectorParams(size=self.embedder.dimensions, distance=models.Distance.COSINE),
                })
            points = []
            for index, (text, vector) in enumerate(zip(paragraphs, vectors)):
                chunk_id = str(uuid5(NAMESPACE_URL, f"{document.document_id}:{revision}:{index}"))
                points.append(models.PointStruct(id=chunk_id, vector={self.vector_name: vector}, payload={
                    **metadata, "revision": revision, "text": text,
                    "reviewed_ordinal": document.reviewed_on.toordinal(),
                    "valid_until_ordinal": document.valid_until.toordinal(),
                }))
            self.client.upsert(self.collection, points=points, wait=True)
            self.client.delete(self.collection, points_selector=models.FilterSelector(filter=models.Filter(
                must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document.document_id))],
                must_not=[models.FieldCondition(key="revision", match=models.MatchValue(value=revision))],
            )), wait=True)
        return len(points)

    def revoke(self, document_id: str):
        with self.lock:
            if self._exists():
                self.client.delete(self.collection, points_selector=models.FilterSelector(filter=models.Filter(
                    must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))],
                )), wait=True)

    def search(self, query: str, age_months: int, topic: str, as_of, top_k=3, min_score=0.55, *, strategy=None):
        if not query.strip() or len(query) > 500 or not 1 <= top_k <= 5:
            raise ValueError("检索参数超出范围")
        with self.lock:
            if not self._exists():
                return []
            self._check_signature()
            # 历史查询不引用当时尚未审核的资料；已过期的当前资料也不再引用。
            metadata_filter = models.Filter(must=[
                    models.FieldCondition(key="review_status", match=models.MatchValue(value="approved")),
                    models.FieldCondition(key="scope", match=models.MatchValue(value="general_education")),
                    models.FieldCondition(key="topics", match=models.MatchValue(value=topic)),
                    models.FieldCondition(key="age_min_months", range=models.Range(lte=age_months)),
                    models.FieldCondition(key="age_max_months", range=models.Range(gte=age_months)),
                    models.FieldCondition(key="reviewed_ordinal", range=models.Range(lte=as_of.toordinal())),
                    models.FieldCondition(key="valid_until_ordinal", range=models.Range(gte=max(as_of, advisor_today()).toordinal())),
                ])

            def decode(point, score=None):
                payload = point.payload or {}
                # 对存量/人工改动的索引再做契约校验，不能仅信任向量相似度。
                document = KnowledgeDocument.model_validate({
                    **{key: payload[key] for key in KnowledgeDocument.model_fields if key != "content"},
                    "content": payload["text"],
                })
                if (not document.age_min_months <= age_months <= document.age_max_months
                        or topic not in document.topics or document.reviewed_on > as_of
                        or document.valid_until < max(as_of, advisor_today())):
                    raise ValueError("索引过滤字段与文献实际元数据不一致")
                return {
                    "id": f"knowledge:{point.id}", "document_id": document.document_id,
                    "text": payload["text"], "title": document.title,
                    "url": str(document.source_url), "version": document.version,
                    "reviewed_on": document.reviewed_on.isoformat(),
                    "score": round(score, 5) if score is not None else None,
                }

            def dense(limit, threshold):
                result = self.client.query_points(
                    self.collection, query=self._embed([query])[0], using=self.vector_name,
                    query_filter=metadata_filter, limit=limit, score_threshold=threshold, with_vectors=False,
                )
                return [decode(point, point.score) for point in result.points]

            def lexical(limit):
                points, next_page = self.client.scroll(
                    self.collection, scroll_filter=metadata_filter, limit=limit,
                    with_payload=True, with_vectors=False,
                )
                if next_page is not None or len(points) > settings.RAG_LEXICAL_SCAN_LIMIT:
                    raise ValueError("字面召回超过有界扫描上限")
                return [decode(point) for point in points]

            return retrieve_candidates(
                query, dense, lexical, strategy=strategy or settings.RAG_RETRIEVAL_STRATEGY,
                top_k=top_k, min_score=min_score, candidate_top_k=settings.RAG_CANDIDATE_TOP_K,
                candidate_min_score=settings.RAG_CANDIDATE_MIN_SCORE,
                lexical_scan_limit=settings.RAG_LEXICAL_SCAN_LIMIT,
            )


@lru_cache(maxsize=1)
def get_knowledge_store() -> KnowledgeStore:
    if settings.QDRANT_URL:
        client = QdrantClient(url=settings.QDRANT_URL,
                              api_key=settings.QDRANT_API_KEY.get_secret_value() or None, timeout=10)
    else:
        path = Path(settings.QDRANT_PATH)
        path.mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=str(path), force_disable_check_same_thread=True)
    return KnowledgeStore(client, OpenAIEmbeddings(), settings.QDRANT_COLLECTION)
