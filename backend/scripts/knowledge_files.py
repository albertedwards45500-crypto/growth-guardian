"""离线知识文件预校验，不读取业务库、不创建索引、不发送Embedding。"""

import json
from pathlib import Path

from app.schemas.advisor import advisor_today
from app.schemas.knowledge import KnowledgeDocument


def load_documents(path: Path) -> list[KnowledgeDocument]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise ValueError("文件须为1至100篇公共审核文献的JSON数组")
    documents = [KnowledgeDocument.model_validate(item) for item in raw]
    if len({item.document_id for item in documents}) != len(documents):
        raise ValueError("同一文件不能重复 document_id")
    if any(item.valid_until < advisor_today() for item in documents):
        raise ValueError("不能导入已过期文献")
    return documents
