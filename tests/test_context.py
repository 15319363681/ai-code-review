from ai_review.context import build_review_code, get_file_context


def test_context_missing_file_returns_empty():
    assert get_file_context("no/such/file.py", 10) == ""


def test_build_review_code_includes_added_lines():
    text = build_review_code("examples/sample.py", [(12, 'query = "SELECT" + user_id')])
    assert "SELECT" in text
    assert "【新增代码】" in text
