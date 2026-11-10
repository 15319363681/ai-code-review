from ai_review.diff_parser import parse_diff
from ai_review.static_check import check_all


def test_static_finds_sql_injection_and_secret():
    text = open("examples/sample.diff", encoding="utf-8").read()
    findings = check_all(parse_diff(text))
    titles = [f["title"] for f in findings]
    assert any("SQL" in t for t in titles)
    assert any("密钥" in t for t in titles)
