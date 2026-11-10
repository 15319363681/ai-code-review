"""编排层：合并静态 + LLM 结果，去重、打分、过滤误报。

这是最容易被忽略、但最能体现水平的一层：
- 同一个问题静态和 LLM 都报了，只留一个
- 置信度低的直接过滤掉，宁可少报也不乱报
- 按严重程度排序，方便在 PR 里展示
"""
from __future__ import annotations

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
    text: str, use_llm: bool = False, min_confidence: float = 0.7, repo_root: str = "."
) -> list[dict]:
    files: list[FileDiff] = parse_diff(text)
    findings = check_all(files)

    if use_llm:
        for f in files:
            # v2：不只发 diff 行，还发完整文件上下文
            code = build_review_code(f.path, f.added_lines, repo_root=repo_root)
            if code.strip():
                findings.extend(review_with_llm(f.path, code))

    findings = dedupe(findings)
    # 过滤低置信度误报
    findings = [f for f in findings if f.get("confidence", 0) >= min_confidence]
    findings.sort(key=lambda x: (SEVERITY_RANK.get(x["severity"], 9), x["file"], x.get("line") or 0))
    return findings
