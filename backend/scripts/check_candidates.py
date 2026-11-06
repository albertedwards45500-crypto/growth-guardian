"""校验待审核公共资料草稿；不调用Embedding，不创建或写入索引。"""

import argparse
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.knowledge_candidate import KnowledgeCandidate


def load_candidates(path: Path) -> list[KnowledgeCandidate]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100:
        raise ValueError("草稿文件须为1至100条公共资料")
    candidates = [KnowledgeCandidate.model_validate(item) for item in raw]
    if len({item.document_id for item in candidates}) != len(candidates):
        raise ValueError("草稿中的document_id不能重复")
    return candidates


def main(argv=None) -> int:
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    candidates = load_candidates(args.file)
    paragraphs = sum(len([part for part in item.content.split("\n\n") if part.strip()]) for item in candidates)
    print(f"草稿校验通过：{len(candidates)} 条资料、{paragraphs} 个段落；review_status=pending，未调用Embedding，未写入索引。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("草稿校验失败：请检查JSON格式、来源地址、段落长度和审核说明。", file=sys.stderr)
        raise SystemExit(1)
