"""编排层：合并静态 + LLM 结果，去重、打分、过滤误报。

这是最容易被忽略、但最能体现水平的一层：
- 同一个问题静态和 LLM 都报了，只留一个
- 置信度低的直接过滤掉，宁可少报也不乱报
- 按严重程度排序，方便在 PR 里展示
- v3：LLM 上下文里加上调用方（callgraph），可选自动修复（autofix，
  只有沙箱验证通过的修复才会标 fix_validated=True）
- v4：按 hunk 增量审查 + 缓存（cache），没变过的 hunk 直接读缓存，
  只有变过的 hunk 才重新审查；缓存文件默认是 .ai_review_cache.json
"""
from __future__ import annotations

import copy

from .autofix import suggest_fix, validate_fix
from .cache import compute_hunk_key, default_cache_path, load_cache, save_cache
from .callgraph import build_caller_context
from .context import build_review_code
from .diff_parser import FileDiff, parse_diff
from .llm_reviewer import review_with_llm
from .static_check import check_all

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def dedupe(findings: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for f in findings:
        key = (f["file"], f.get("line"), f["title"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def review_diff_text(
    text: str,
    use_llm: bool = False,
    min_confidence: float = 0.7,
    repo_root: str = ".",
    include_fixes: bool = False,
    use_cache: bool = True,
    cache_path: str | None = None,
) -> list[dict]:
    files: list[FileDiff] = parse_diff(text)
    cache_file = cache_path if cache_path is not None else str(default_cache_path(repo_root))
    cache: dict = load_cache(cache_file) if use_cache else {}
    dirty = False
    findings: list[dict] = []

    for f in files:
        for hunk in f.hunks:
            key = compute_hunk_key(f.path, hunk.lines, use_llm=use_llm)
            if use_cache and key in cache:
                findings.extend(copy.deepcopy(cache[key]))
                continue
            sub = FileDiff(path=f.path, hunks=[hunk])
            hunk_findings = check_all([sub])
            if use_llm:
                # v2 完整文件上下文 + v3 调用方上下文（本地文件存在时才有）
                code = build_review_code(f.path, hunk.added_lines, repo_root=repo_root)
                callers = build_caller_context(f.path, hunk.added_lines, repo_root=repo_root)
                if callers:
                    code += callers
                if code.strip():
                    hunk_findings.extend(review_with_llm(f.path, code))
            if use_cache:
                cache[key] = copy.deepcopy(hunk_findings)
                dirty = True
            findings.extend(hunk_findings)

    if use_cache and dirty:
        save_cache(cache_file, cache)

    findings = dedupe(findings)
    # 过滤低置信度误报
    findings = [f for f in findings if f.get("confidence", 0) >= min_confidence]
    findings.sort(key=lambda x: (SEVERITY_RANK.get(x["severity"], 9), x["file"], x.get("line") or 0))

    if include_fixes:
        for f in findings:
            fix = suggest_fix(f)
            if fix is None:
                f["fix"] = None
                f["fix_validated"] = False
            else:
                f["fix"] = fix
                f["fix_validated"] = validate_fix({**f, "fix": fix}, repo_root=repo_root)

    return findings
