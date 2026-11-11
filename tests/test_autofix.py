"""v3：自动修复 + 沙箱验证测试。"""
from pathlib import Path

from ai_review.autofix import suggest_fix, validate_fix
from ai_review.reviewer import review_diff_text


def _finding(title, detail, file="examples/sample.py", line=12):
    return {"file": file, "line": line, "title": title, "detail": detail}


def test_suggest_fix_sql_injection():
    fix = suggest_fix(_finding("SQL 拼接存在注入风险", 'query = "SELECT * FROM users WHERE id = " + user_id'))
    assert fix is not None
    assert "%s" in fix
    assert "+" not in fix.split("execute")[1].split('"')[1] or "%s" in fix


def test_suggest_fix_secret_uses_environ():
    fix = suggest_fix(_finding("疑似硬编码密钥", 'api_key = "sk-live-123456"', line=14))
    assert fix is not None
    assert "os.environ" in fix
    assert "sk-live" not in fix


def test_suggest_fix_empty_except():
    fix = suggest_fix(_finding("空 except 会吞掉错误", "except:", line=17))
    assert fix is not None
    assert "raise" in fix


def test_suggest_fix_eval_exec():
    fix = suggest_fix(_finding("eval / exec 执行任意代码", "result = eval(user_input)"))
    assert fix is not None
    assert "literal_eval" in fix


def test_suggest_fix_unknown_returns_none():
    assert suggest_fix(_finding("未知问题", "x = 1")) is None


def test_validate_fix_in_real_file(tmp_path):
    p = tmp_path / "bad.py"
    p.write_text(
        'query = "SELECT * FROM users WHERE id = " + user_id\n'
        'api_key = "sk-live-123456"\n',
        encoding="utf-8",
    )
    f = _finding("SQL 拼接存在注入风险", 'query = "SELECT * FROM users WHERE id = " + user_id', file="bad.py", line=1)
    f["fix"] = suggest_fix(f)
    assert validate_fix(f, repo_root=str(tmp_path)) is True


def test_review_with_fixes_marks_all_validated():
    findings = review_diff_text(
        Path("examples/sample.diff").read_text(encoding="utf-8"),
        use_llm=False, include_fixes=True,
    )
    assert len(findings) == 3
    for f in findings:
        assert f.get("fix"), f
        assert f.get("fix_validated") is True, f
