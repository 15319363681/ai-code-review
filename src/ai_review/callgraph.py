"""调用链检索：只看 diff 会漏掉“这个函数被谁调用”。

v3 做法：用 ast 解析 repo_root 下的 Python 文件，建立
函数定义表和调用关系；对 diff 里改动的函数，找出它的调用方，
把调用方的代码片段一起发给 LLM 做上下文。
文件不存在 / 解析失败时不编造调用方，返回空列表。
"""
from __future__ import annotations

import ast
from pathlib import Path


def _iter_py_files(repo_root: str) -> list[Path]:
    root = Path(repo_root)
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*.py")):
        # 跳过虚拟环境、缓存和隐藏目录
        parts = set(p.relative_to(root).parts)
        if parts & {".venv", "venv", "__pycache__", ".git", "node_modules"}:
            continue
        out.append(p)
    return out


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def collect_definitions(repo_root: str) -> dict[str, list[dict]]:
    """函数名 -> [{file, line, end_line}]，file 为相对 repo_root 的路径。"""
    defs: dict[str, list[dict]] = {}
    for p in _iter_py_files(repo_root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        rel = str(p.relative_to(Path(repo_root)))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.setdefault(node.name, []).append(
                    {
                        "file": rel,
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                    }
                )
    return defs


def _caller_snippet(path: Path, line_no: int, window: int = 3) -> str:
    lines = _read_lines(path)
    if not lines or line_no < 1 or line_no > len(lines):
        return ""
    start = max(0, line_no - window - 1)
    end = min(len(lines), line_no + window)
    out = []
    for i in range(start, end):
        marker = ">>>" if i + 1 == line_no else "   "
        out.append(f"{marker} {i + 1}: {lines[i]}")
    return "\n".join(out)


def find_callers(func_name: str, repo_root: str) -> list[dict]:
    """找出所有调用 func_name 的地方，每项带调用方函数、文件、行号和代码片段。"""
    callers: list[dict] = []
    for p in _iter_py_files(repo_root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        rel = str(p.relative_to(Path(repo_root)))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            caller = node.name
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                called = None
                func = child.func
                if isinstance(func, ast.Name):
                    called = func.id
                elif isinstance(func, ast.Attribute):
                    called = func.attr
                if called == func_name:
                    callers.append(
                        {
                            "function": func_name,
                            "caller_function": caller,
                            "caller_file": rel,
                            "caller_line": child.lineno,
                            "snippet": _caller_snippet(p, child.lineno),
                        }
                    )
    return callers


def changed_functions(path: str, added_lines: list[tuple[int, str]], repo_root: str = ".") -> list[str]:
    """diff 里改动的行落在哪些函数定义里。文件不存在时返回空列表。"""
    p = Path(repo_root) / path
    if not p.exists():
        return []
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    changed: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        if any(node.lineno <= ln <= end for ln, _ in added_lines):
            changed.append(node.name)
    return changed


def get_callers_for_diff(
    path: str, added_lines: list[tuple[int, str]], repo_root: str = "."
) -> list[dict]:
    """对一次 diff，返回改动函数的调用方列表；本地文件不存在时返回 []。"""
    funcs = changed_functions(path, added_lines, repo_root=repo_root)
    out: list[dict] = []
    seen: set[tuple] = set()
    for name in funcs:
        for c in find_callers(name, repo_root):
            # 不把改动函数自身的递归调用算作调用方上下文
            if c["caller_file"] == path and c["caller_function"] == name:
                continue
            key = (c["caller_file"], c["caller_line"], c["function"])
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


def build_caller_context(
    path: str, added_lines: list[tuple[int, str]], repo_root: str = "."
) -> str:
    """把调用方片段拼成一段可发给 LLM 的文本；没有调用方时返回空字符串。"""
    callers = get_callers_for_diff(path, added_lines, repo_root=repo_root)
    if not callers:
        return ""
    parts = ["\n【调用方上下文（改动函数的调用者）】"]
    for c in callers:
        parts.append(
            f"- {c['function']} 被 {c['caller_file']}:{c['caller_line']} "
            f"（{c['caller_function']}）调用："
        )
        if c["snippet"]:
            parts.append(c["snippet"])
    return "\n".join(parts)
