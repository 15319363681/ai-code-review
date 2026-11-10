"""GitHub API：拉 PR diff、发逐行评论。

注意：行号定位是工程难点之一，PR 更新后行号会变，
v1 先做基础版：按 diff 里的新行号发评论，v2 再做增量审查。
"""
from __future__ import annotations

import os

import requests

API = "https://api.github.com"


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def get_pr_diff(repo: str, pr_number: int) -> str:
    url = f"{API}/repos/{repo}/pulls/{pr_number}"
    r = requests.get(url, headers={**_headers(), "Accept": "application/vnd.github.diff"}, timeout=30)
    r.raise_for_status()
    return r.text


def post_review_comment(repo: str, pr_number: int, commit_sha: str, findings: list[dict]) -> None:
    """发一条汇总评论（v1 简化版，不逐行，先保证能跑通）。"""
    if not findings:
        body = "AI 代码审查完成：没有发现高置信度问题 ✅"
    else:
        lines = ["## AI 代码审查\n"]
        for f in findings:
            lines.append(
                f"- **[{f['severity']}] {f['title']}** — `{f['file']}:{f.get('line')}`\n"
                f"  {f['detail']}\n  建议：{f['suggestion']}\n"
            )
        body = "\n".join(lines)
    url = f"{API}/repos/{repo}/issues/{pr_number}/comments"
    r = requests.post(url, headers=_headers(), json={"body": body}, timeout=30)
    r.raise_for_status()
