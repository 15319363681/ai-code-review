from ai_review.diff_parser import parse_diff


def test_parse_sample():
    text = open("examples/sample.diff", encoding="utf-8").read()
    files = parse_diff(text)
    assert len(files) == 1
    assert files[0].path == "examples/sample.py"
    assert len(files[0].added_lines) >= 3
