"""增量审查 + 缓存：大 PR 不用每次全量重审。

v4 做法：按 diff hunk（文件 + hunk 内容）算哈希，把每个 hunk 的
审查结果缓存在 .ai_review_cache.json 里；第二次跑时，没变过的
hunk 直接读缓存，只有变过的 hunk 才重新审查。缓存只存静态 +
LLM 的基础结果，自动修复（fix / fix_validated）在缓存读取后
再算，不进缓存。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CACHE_FILENAME = ".ai_review_cache.json"
CACHE_VERSION = "v1"


def compute_hunk_key(file_path: str, hunk_lines: list[str], use_llm: bool = False) -> str:
    """hunk 的缓存键：版本 + 是否用 LLM + 文件 + hunk 原始行。"""
    payload = json.dumps(
        [CACHE_VERSION, bool(use_llm), file_path, list(hunk_lines)],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_cache_path(repo_root: str = ".") -> Path:
    return Path(repo_root) / CACHE_FILENAME


def load_cache(cache_path: str | Path) -> dict:
    p = Path(cache_path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(cache_path: str | Path, cache: dict) -> None:
    p = Path(cache_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
