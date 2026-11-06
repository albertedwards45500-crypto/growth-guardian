"""离线导入/撤销已审核公共知识，不连接宝宝业务数据库。"""

import argparse
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.knowledge import get_knowledge_store
from scripts.knowledge_files import load_documents


def main(argv=None):
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description="导入已审核公共文献JSON数组，或撤销一个document_id")
    parser.add_argument("file", nargs="?", type=Path)
    parser.add_argument("--revoke", metavar="DOCUMENT_ID")
    parser.add_argument("--check", action="store_true", help="仅校验整个文件，不访问Embedding或向量库")
    args = parser.parse_args(argv)
    if bool(args.file) == bool(args.revoke):
        parser.error("请提供一个JSON文件，或使用 --revoke DOCUMENT_ID")
    if args.check and not args.file:
        parser.error("--check 仅用于文献文件")
    documents = []
    if args.file:
        documents = load_documents(args.file)
        if args.check:
            count = sum(len([part for part in item.content.split("\n\n") if part.strip()]) for item in documents)
            print(f"格式校验通过：{len(documents)} 篇文献、{count} 个完整段落；未调用Embedding，未创建或写入索引。")
            return
        if not settings.RAG_EMBEDDING_API_KEY.get_secret_value():
            parser.error("请通过环境变量配置 RAG_EMBEDDING_API_KEY")
    store = get_knowledge_store()
    try:
        if args.revoke:
            store.revoke(args.revoke)
            print("指定文献已撤销。")
        else:
            count = sum(store.ingest(document) for document in documents)
            print(f"已导入 {len(documents)} 篇审核文献、{count} 个完整段落。")
    finally:
        store.client.close()
        get_knowledge_store.cache_clear()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # SDK/校验异常可能含密钥或正文，不输出原始异常。
        print("操作失败：请检查文献契约、模型维度、密钥配置和向量库连接。", file=sys.stderr)
        raise SystemExit(1)
