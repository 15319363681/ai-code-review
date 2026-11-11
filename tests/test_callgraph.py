"""v3：调用链检索测试。"""
from pathlib import Path

from ai_review.callgraph import (
    build_caller_context,
    changed_functions,
    find_callers,
    get_callers_for_diff,
)


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / "a.py").write_text(
        "def get_user(user_id):\n"
        "    query = \"SELECT * FROM users WHERE id = \" + user_id\n"
        "    return query\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "from a import get_user\n"
        "\n"
        "\n"
        "def show():\n"
        "    return get_user(1)\n",
        encoding="utf-8",
    )
    return tmp_path


def test_find_callers_finds_b(tmp_path):
    repo = _make_repo(tmp_path)
    callers = find_callers("get_user", str(repo))
    assert len(callers) == 1
    assert callers[0]["caller_file"] == "b.py"
    assert callers[0]["caller_function"] == "show"
    assert "get_user(1)" in callers[0]["snippet"]


def test_changed_functions_and_callers_for_diff(tmp_path):
    repo = _make_repo(tmp_path)
    added = [(2, '    query = "SELECT * FROM users WHERE id = " + user_id')]
    assert changed_functions("a.py", added, repo_root=str(repo)) == ["get_user"]
    callers = get_callers_for_diff("a.py", added, repo_root=str(repo))
    assert len(callers) == 1
    assert callers[0]["caller_file"] == "b.py"
    ctx = build_caller_context("a.py", added, repo_root=str(repo))
    assert "调用方" in ctx
    assert "b.py" in ctx


def test_missing_file_returns_no_callers(tmp_path):
    assert get_callers_for_diff("no/such.py", [(1, "x = 1")], repo_root=str(tmp_path)) == []
    assert build_caller_context("no/such.py", [(1, "x = 1")], repo_root=str(tmp_path)) == ""
    assert find_callers("whatever", str(tmp_path)) == []
