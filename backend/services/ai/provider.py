"""Model HTTP boundary. Credentials travel only in the request header."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
from fastapi import HTTPException
from deepseek_harness_runtime import resolve_bundled_launch_args

from .catalog import runtime_route

def json_object(text):
    """Best-effort JSON object extraction from a model answer.

    Models wrap JSON in code fences, prepend a sentence, or double-encode it as
    a string; all three used to surface as "AI 返回的数据格式不完整".
    """
    if not isinstance(text, str):
        raise ValueError("text required")
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else value
        value = value.rsplit("```", 1)[0] if "```" in value else value
        value = value.strip()
    candidates = [value]
    start, end = value.find("{"), value.rfind("}")
    if 0 <= start < end:
        candidates.append(value[start:end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except (TypeError, ValueError):
                continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("JSON object required")

# The embedded iOS build has no subprocess, so the Harness adapters are
# unavailable there; the app talks to the provider over HTTP instead.
EMBEDDED = sys.platform == "ios"


def _completion_url(config):
    base = (config.get("base_url") or "").rstrip("/")
    if not base:
        raise HTTPException(409, "本地版请在 AI 设置里使用“自定义模型 API”填写兼容 OpenAI 的地址。")
    if config.get("protocol", "openai-completions") != "openai-completions":
        raise HTTPException(409, "本地版目前只支持 OpenAI 兼容的 chat/completions 协议。")
    return base + "/chat/completions"


def _wire_messages(messages):
    """Translate the internal content parts to OpenAI's chat format."""
    wired = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if part.get("type") == "text":
                    parts.append({"type": "text", "text": part.get("text", "")})
                elif part.get("type") == "image":
                    parts.append({"type": "image_url",
                                  "image_url": {"url": f"data:{part.get('media_type', 'image/png')};base64,{part.get('data', '')}"}})
            wired.append({**message, "content": parts})
        else:
            wired.append(message)
    return wired


def complete_openai(messages, config, api_key, format="text", transport=None, *, check_cancelled=lambda: None):
    """One model call against any OpenAI-compatible endpoint."""
    check_cancelled()
    payload = {"model": config["model"], "messages": _wire_messages(messages), "stream": False}
    if format == "json":
        payload["messages"] = [{"role": "system", "content": "请将回答输出为一个合法的 JSON 对象。"}, *payload["messages"]]
        payload["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    try:
        with httpx.Client(timeout=90, transport=transport) as client:
            response = client.post(_completion_url(config), headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            choice = result["choices"][0]
            if choice.get("finish_reason") not in (None, "stop"):
                raise HTTPException(502, "AI 回答未完整生成，请缩小内容范围后重试。")
            content = choice["message"]["content"]
            if format == "json":
                content = json_object(content)
            usage = result.get("usage") or {}
            check_cancelled()
            return {"content": content, "model": config["model"],
                    "usage": {field: usage.get(field, 0) for field in ("prompt_tokens", "completion_tokens", "total_tokens")}}
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        message = {401: "模型 API Key 未通过验证，请在设置中更新。", 402: "模型账户余额不足。",
                   429: "模型请求过于频繁，请稍后重试。"}.get(code, f"模型请求失败（HTTP {code}）。")
        raise HTTPException(502, message) from None
    except httpx.HTTPError:
        raise HTTPException(502, "暂时无法连接模型服务，请检查地址与网络后重试。") from None
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(502, "AI 返回的数据格式不完整，请重试。") from None


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
                content = json_object(content)
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


def complete_with_harness(messages, config, api_key, runtime_root, format='text', *, check_cancelled=lambda: None):
    """One model call through the same official adapter as plugin workflows."""
    if EMBEDDED:
        return complete_openai(messages, config, api_key, format, check_cancelled=check_cancelled)
    temporary = runtime_root / 'tmp'
    temporary.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ai-text-', dir=temporary) as name:
        directory = Path(name)
        route, rows = runtime_route(config)
        output = directory / 'response.json'
        instructions = [{'role': 'system', 'content': '请将回答输出为一个合法的 JSON 对象。'}] if format == 'json' else []
        if config.get('image_input'):
            rows.append({'insert': [{'id': 'campus-image-storage', 'name': '@deepseek-ai/dsh-attachment-local'}]})
        entry = 'image-completion.mjs' if config.get('image_input') else 'completion.mjs'
        rows.append({'insert': [{'id': 'campus-completion', 'name': str(Path(__file__).with_name(entry)),
                     'config': {'provider': route, 'model': config['model'], 'messages': [*instructions, *messages], 'output': str(output)}}]})
        patch = directory / 'request.patch.yml'
        patch.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        env = {**os.environ, 'DSH_HOME': str(directory / 'home'), 'CAMPUS_AI_API_KEY': api_key,
               'TMP': str(temporary), 'TEMP': str(temporary), 'TMPDIR': str(temporary)}
        try:
            from .harness import prepare
            prepare([*resolve_bundled_launch_args(), '--profile', 'sdk-minimal', '--patch', str(patch)],
                    cwd=directory, env=env, timeout=120, check_cancelled=check_cancelled)
            result = json.loads(output.read_text(encoding='utf-8'))
            if result.get('finish') != 'stop':
                raise HTTPException(502, 'AI 回答未完整生成，请检查模型配置、凭据或网络后重试。')
            content = json.loads(result['content']) if format == 'json' else result['content']
            if format == 'json' and not isinstance(content, dict):
                raise ValueError('JSON object required')
            return {'content': content, 'model': config['model'], 'usage': result['usage']}
        except subprocess.TimeoutExpired:
            raise HTTPException(504, 'AI 请求超时，请稍后重试。') from None
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            raise HTTPException(502, 'AI 请求失败，请检查所选提供商的模型、凭据与网络连接。') from None
