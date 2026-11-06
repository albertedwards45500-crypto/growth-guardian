"""最小模型连通检查；只发送固定测试文本，不读取宝宝数据库，不输出密钥。"""

import argparse
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import APIConnectionError, APIStatusError, OpenAI

from app.core.config import settings
from app.services.advisor_agent import ResponsesModel


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", action="store_true", help="额外验证两轮工具调用与结构化输出，会产生少量模型费用")
    args = parser.parse_args()
    if not settings.OPENAI_API_KEY.get_secret_value() or not settings.ADVISOR_MODEL:
        print(json.dumps({"status": "not_configured"}))
        return 1
    with OpenAI(api_key=settings.OPENAI_API_KEY.get_secret_value(), base_url=settings.OPENAI_BASE_URL,
                timeout=settings.ADVISOR_MODEL_TIMEOUT_SECONDS, max_retries=0) as client:
        ids = [item.id for item in client.models.list().data]
    available = settings.ADVISOR_MODEL in ids
    if not available:
        print(json.dumps({"status": "model_not_available", "requested_model": settings.ADVISOR_MODEL}))
        return 1
    if args.tools:
        definitions = [{"type": "function", "name": "check_connection",
                        "description": "返回固定连通性测试标记，不读取或更改任何业务数据。", "strict": True,
                        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}}]
        inputs = [{"role": "user", "content": '这是固定连通测试：先调用check_connection工具，然后返回JSON {"knowledge_ids":[]}。'}]
        model = ResponsesModel()
        first = model.respond(inputs, definitions)
        if not first.calls or any(call["name"] != "check_connection" or json.loads(call["arguments"]) != {} for call in first.calls):
            raise ValueError("工具测试未通过")
        inputs += first.output
        inputs += [{"type": "function_call_output", "call_id": call["call_id"], "output": '{"connected":true}'} for call in first.calls]
        final = model.respond(inputs, definitions)
        if final.calls or final.selection is None or final.selection.knowledge_ids:
            raise ValueError("结构化输出测试未通过")
    print(json.dumps({"status": "ok", "model": settings.ADVISOR_MODEL, "tool_roundtrip_verified": args.tools}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except APIStatusError as error:
        print(json.dumps({"status": "http_error", "status_code": error.status_code}))
    except APIConnectionError:
        print(json.dumps({"status": "connection_error"}))
    except Exception:
        print(json.dumps({"status": "validation_or_configuration_error"}))
    raise SystemExit(1)
