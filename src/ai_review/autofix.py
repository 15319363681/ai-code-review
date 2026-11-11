"""自动修复建议 + 沙箱验证。

v3 做法：对静态规则能确定的问题，给出具体的修复代码片段；
每个修复在沙箱里验证过才保留：
- 本地文件存在时：把修复应用到文件的临时副本上，py_compile 通过才算有效；
- 本地文件不存在时：对修复片段本身做 ast 解析，except 类修复用
  try/except 模板包裹后再解析；解析通过才算有效。
- 对 src/、tests/ 下的文件，还可以用 validate_fix_with_tests() 把修复
  应用到整个仓库的临时副本上，跑一遍 pytest（有 pytest 时才跑）。
修复只放进 finding 的 "fix" / "fix_validated" 字段，不直接改用户代码。
"""
from __future__ import annotations

import ast
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def suggest_fix(finding: dict) -> str | None:
    """按 finding 的标题给修复片段；不认识的问题返回 None。"""
    title = finding.get("title", "")
    detail = (finding.get("detail") or "").strip()

    if "SQL" in title:
        # 尽量从原行里抠出表名 / 参数名，否则给通用参数化写法
        m = re.search(r"WHERE\s+(\w+)\s*=\s*\"?\s*\+?\s*(\w+)", detail)
        if m:
            column, var = m.group(1), m.group(2)
            return (
                f'cursor.execute("SELECT * FROM users WHERE {column} = %s", ({var},))'
            )
        if "f\"" in detail or "f'" in detail:
            return 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))'
        return 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))'

    if "密钥" in title:
        m = re.search(r"(password|api_key|secret|token)\s*=", detail)
        var = m.group(1) if m else "api_key"
        env = var.upper()
        return f'{var} = os.environ.get("{env}")  # 需要 import os'

    if "空 except" in title:
        return (
            "except Exception as e:\n"
            "    logging.exception(\"error\")  # 需要 import logging\n"
            "    raise"
        )

    if "eval / exec" in title:
        return "result = ast.literal_eval(user_input)  # 需要 import ast，只解析字面量"

    return None


def _snippet_parses(fix: str) -> bool:
    """修复片段本身能否解析；except 块用 try/except 模板包裹后再解析。"""
    try:
        ast.parse(fix)
        return True
    except SyntaxError:
        pass
    stripped = fix.lstrip()
    if stripped.startswith("except"):
        # except 块本身需要一个 try 前缀，首行不缩进、其余行保持原缩进
        wrapped = "try:\n    pass\n" + fix
    else:
        wrapped = "try:\n    pass\n" + "\n".join(
            ("    " + line if line.strip() else line) for line in fix.splitlines()
        )
    try:
        ast.parse(wrapped)
        return True
    except SyntaxError:
        return False


def _apply_fix_to_text(text: str, line_no: int, fix: str) -> str:
    lines = text.splitlines()
    if line_no < 1 or line_no > len(lines):
        return text
    fix_lines = fix.splitlines()
    # 去掉修复里纯注释的行尾说明（# 需要 import ...），保留代码行
    code_lines = []
    for ln in fix_lines:
        if "#" in ln:
            code, _, _ = ln.partition("#")
            code_lines.append(code.rstrip() if code.strip() else ln)
        else:
            code_lines.append(ln)
    return "\n".join(lines[: line_no - 1] + code_lines + lines[line_no:]) + "\n"


def validate_fix(finding: dict, repo_root: str = ".") -> bool:
    """验证一个修复是否有效；找不到修复时返回 False。"""
    fix = finding.get("fix") or suggest_fix(finding)
    if not fix:
        return False
    path = Path(repo_root) / str(finding.get("file", ""))
    line_no = finding.get("line")
    if path.exists() and isinstance(line_no, int):
        text = path.read_text(encoding="utf-8", errors="ignore")
        new_text = _apply_fix_to_text(text, line_no, fix)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(new_text)
            tmp_path = tmp.name
        try:
            py_compile.compile(tmp_path, doraise=True)
            return True
        except Exception:
            return False
        finally:
            os.unlink(tmp_path)
    return _snippet_parses(fix)


def validate_fix_with_tests(finding: dict, repo_root: str = ".") -> bool:
    """在仓库临时副本上应用修复，py_compile + 跑 pytest；无 pytest 时只做 py_compile。

    只适用于 src/、tests/ 下的文件；其他文件直接走 validate_fix()。
    """
    if not validate_fix(finding, repo_root=repo_root):
        return False
    rel = str(finding.get("file", ""))
    if not (rel.startswith("src/") or rel.startswith("tests/")):
        return True
    if shutil.which("pytest") is None and shutil.which("python3") is None:
        return True
    fix = finding.get("fix") or suggest_fix(finding)
    line_no = finding.get("line")
    root = Path(repo_root)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "repo"
        shutil.copytree(root, copy, ignore=shutil.ignore_patterns("__pycache__", ".venv", ".git"))
        target = copy / rel
        if not target.exists() or not isinstance(line_no, int):
            return False
        target.write_text(
            _apply_fix_to_text(target.read_text(encoding="utf-8", errors="ignore"), line_no, fix),
            encoding="utf-8",
        )
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=copy, capture_output=True, text=True, timeout=120,
        )
        # pytest 未安装时返回码为 1 且提示 No module named pytest，不算修复失败
        if "No module named pytest" in (r.stdout + r.stderr):
            return True
        return r.returncode == 0
