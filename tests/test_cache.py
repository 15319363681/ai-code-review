"""v4：增量审查 + 缓存测试。"""
import json
from pathlib import Path

from ai_review.cache import compute_hunk_key, load_cache, save_cache
from ai_review.reviewer import review_diff_text


def test_hunk_key_stable_and_changes():
    k1 = compute_hunk_key("a.py", ["+x = 1"])
    k2 = compute_hunk_key("a.py", ["+x = 1"])
    k3 = compute_hunk_key("a.py", ["+x = 2"])
    k4 = compute_hunk_key("b.py", ["+x = 1"])
    assert k1 == k2
    assert k1 != k3
    assert k1 != k4


def test_cache_roundtrip(tmp_path):
    p = tmp_path / ".ai_review_cache.json"
    save_cache(p, {"abc": [{"title": "t"}]})
    assert load_cache(p) == {"abc": [{"title": "t"}]}
    assert load_cache(tmp_path / "missing.json") == {}


def test_second_run_hits_cache(tmp_path):
    diff = Path("examples/sample.diff").read_text(encoding="utf-8")
    cache_path = str(tmp_path / ".ai_review_cache.json")
    first = review_diff_text(diff, use_llm=False, use_cache=True, cache_path=cache_path)
    assert len(first) == 3
    assert Path(cache_path).exists()
    snapshot = Path(cache_path).read_text(encoding="utf-8")
    assert len(json.loads(snapshot)) == 1  # sample.diff 只有一个 hunk
    second = review_diff_text(diff, use_llm=False, use_cache=True, cache_path=cache_path)
    assert second == first
    # 全命中缓存：缓存文件内容不变（没有新条目写入）
    assert Path(cache_path).read_text(encoding="utf-8") == snapshot


def test_changed_hunk_is_re_reviewed(tmp_path):
    diff = Path("examples/sample.diff").read_text(encoding="utf-8")
    cache_path = str(tmp_path / ".ai_review_cache.json")
    first = review_diff_text(diff, use_llm=False, use_cache=True, cache_path=cache_path)
    assert len(first) == 3
    changed = diff.replace('api_key = "sk-live-123456"', "x = 1")
    second = review_diff_text(changed, use_llm=False, use_cache=True, cache_path=cache_path)
    titles = [f["title"] for f in second]
    assert len(second) == 2
    assert "疑似硬编码密钥" not in titles
    assert len(json.loads(Path(cache_path).read_text(encoding="utf-8"))) == 2


def test_no_cache_does_not_write_file(tmp_path):
    diff = Path("examples/sample.diff").read_text(encoding="utf-8")
    cache_path = str(tmp_path / ".ai_review_cache.json")
    findings = review_diff_text(diff, use_llm=False, use_cache=False, cache_path=cache_path)
    assert len(findings) == 3
    assert not Path(cache_path).exists()
