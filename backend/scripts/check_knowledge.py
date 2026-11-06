"""检查Embedding配置；--probe只发送固定公共测试文本，不读取宝宝库或写索引。"""

import argparse
import json
import logging
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.knowledge import OpenAIEmbeddings


def check_configuration() -> list[str]:
    missing = []
    if not settings.RAG_EMBEDDING_API_KEY.get_secret_value().strip():
        missing.append("RAG_EMBEDDING_API_KEY")
    if not settings.RAG_EMBEDDING_MODEL.strip():
        missing.append("RAG_EMBEDDING_MODEL")
    try:
        endpoint = urlsplit(settings.RAG_EMBEDDING_BASE_URL)
        local = endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
        if not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
            raise ValueError()
        if endpoint.scheme != "https" and not (endpoint.scheme == "http" and local):
            raise ValueError()
    except ValueError:
        missing.append("RAG_EMBEDDING_BASE_URL")
    return missing


def main(argv=None) -> int:
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="发送一条固定测试文本，可能产生少量Embedding费用")
    args = parser.parse_args(argv)
    problems = check_configuration()
    report = {"rag_enabled": settings.RAG_ENABLED, "index_checked": False}
    if problems:
        report.update(status="configuration_incomplete", fields=problems)
        print(json.dumps(report))
        return 1
    if args.probe:
        try:
            OpenAIEmbeddings().embed(["这是公共知识检索的向量服务连通性测试。"])
        except Exception:
            report.update(status="embedding_probe_failed")
            print(json.dumps(report))
            return 1
    report.update(status="ok", embedding_probed=args.probe, dimensions=settings.RAG_EMBEDDING_DIMENSIONS,
                  dimensions_parameter_sent=settings.RAG_EMBEDDING_SEND_DIMENSIONS)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(json.dumps({"status": "configuration_or_validation_error"}))
        raise SystemExit(1)
