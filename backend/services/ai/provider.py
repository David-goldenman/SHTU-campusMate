"""DeepSeek HTTP boundary. Credentials travel only in the request header."""
import json

import httpx
from fastapi import HTTPException


def complete(messages, model, api_key, format="text", transport=None):
    payload = {"model": model, "messages": messages, "thinking": {"type": "disabled"}, "max_tokens": 6000, "stream": False}
    if format == "json":
        payload["messages"] = [{"role": "system", "content": "请将回答输出为一个合法的 JSON 对象。"}, *messages]
        payload["response_format"] = {"type": "json_object"}
    try:
        with httpx.Client(timeout=90, transport=transport) as client:
            response = client.post("https://api.deepseek.com/chat/completions", headers={"Authorization": "Bearer " + api_key}, json=payload)
            response.raise_for_status()
            result = response.json()
            choice = result["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise HTTPException(502, "AI 回答未完整生成，请缩小内容范围后重试。")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("Text content required")
            if format == "json":
                content = json.loads(content)
                if not isinstance(content, dict):
                    raise ValueError("JSON object required")
            usage = result.get("usage") or {}
            return {"content": content, "model": model, "usage": {field: usage.get(field, 0) for field in ("prompt_tokens", "completion_tokens", "total_tokens")}}
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        message = {401: "DeepSeek API Key 未通过验证，请在设置中更新。", 402: "DeepSeek 账户余额不足。", 429: "DeepSeek 请求过于频繁，请稍后重试。"}.get(code, f"DeepSeek 请求失败（HTTP {code}）。")
        raise HTTPException(502, message) from None
    except httpx.HTTPError:
        raise HTTPException(502, "暂时无法连接 DeepSeek，请检查网络后重试。") from None
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(502, "AI 返回的数据格式不完整，请重试。") from None
