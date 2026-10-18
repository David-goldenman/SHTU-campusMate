"""DeepSeek HTTP boundary. Credentials travel only in the request header."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import HTTPException
from deepseek_harness_runtime import resolve_bundled_launch_args

from .catalog import runtime_route


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


def complete_with_harness(messages, config, api_key, runtime_root, format='text', *, check_cancelled=lambda: None):
    """One model call through the same official adapter as plugin workflows."""
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
