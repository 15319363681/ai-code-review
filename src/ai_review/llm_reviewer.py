"""LLM 审查：只负责需要语义理解的部分，输出结构化 JSON。

设计要点（也是这个项目的难点）：
- 只把新增行 + 完整文件上下文（由调用方补全）发给模型，不只发 diff
- 要求模型返回 JSON，方便去重、打分、过滤
- 没有 API Key 时返回空列表，不编造结果；静态检查照常跑
"""
from __future__ import annotations

import json
import os
import urllib.request

PROMPT = """你是一个资深代码审查员。审查下面这段新增代码，只报真实、有把握的问题。
不要报风格小毛病，不要猜测没有证据的问题。
按严重程度分 high / medium / low，类别分 bug / security / performance / style。
只返回 JSON 数组，每项包含：line（行号）, severity, category, title, detail, suggestion, confidence（0-1）。

文件：{path}
新增代码：
{code}
"""


def review_with_llm(path: str, code: str, model: str = "gpt-4o-mini") -> list[dict]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return []

    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": PROMPT.format(path=path, code=code)}],
            "temperature": 0.1,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except Exception:
        return []

    text = data["choices"][0]["message"]["content"]
    # 模型有时会在 JSON 外面包一层 ```json，清理一下
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        items = json.loads(text)
    except Exception:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        out.append(
            {
                "file": path,
                "line": it.get("line"),
                "severity": it.get("severity", "medium"),
                "category": it.get("category", "bug"),
                "title": it.get("title", ""),
                "detail": it.get("detail", ""),
                "suggestion": it.get("suggestion", ""),
                "confidence": float(it.get("confidence", 0.7)),
                "source": "llm",
            }
        )
    return out
