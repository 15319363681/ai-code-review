"""上下文补全：只看 diff 会漏调用方和类型定义。

v2 做法：拿到 diff 里改动的文件和行号后，尽量在本地仓库里
找到这个文件，取改动行前后各 20 行作为上下文，一起发给 LLM。
找不到文件时不报错，只用 diff 本身审查，不编造上下文。
"""
from __future__ import annotations

from pathlib import Path


def get_file_context(path: str, line_no: int, window: int = 20, repo_root: str = ".") -> str:
    p = Path(repo_root) / path
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    start = max(0, line_no - window - 1)
    end = min(len(lines), line_no + window)
    out = []
    for i in range(start, end):
        marker = ">>>" if i + 1 == line_no else "   "
        out.append(f"{marker} {i+1}: {lines[i]}")
    return "\n".join(out)


def build_review_code(path: str, added_lines: list[tuple[int, str]], repo_root: str = ".") -> str:
    """把新增行 + 它们周围的完整文件上下文拼成一段给 LLM 看的文本。"""
    parts = ["【新增代码】"]
    for ln, content in added_lines:
        parts.append(f"{ln}: {content}")
    parts.append("\n【完整文件上下文（改动行前后 20 行）】")
    seen = set()
    for ln, _ in added_lines:
        if ln in seen:
            continue
        seen.add(ln)
        ctx = get_file_context(path, ln, repo_root=repo_root)
        if ctx:
            parts.append(ctx)
            parts.append("---")
    return "\n".join(parts)
