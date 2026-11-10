"""命令行入口：review 本地 diff / review-pr 拉 GitHub PR。"""
from __future__ import annotations

import argparse
import json
import sys

from .github_client import get_pr_diff, post_review_comment
from .reviewer import review_diff_text


def main() -> None:
    p = argparse.ArgumentParser(prog="ai-review")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("review", help="审查本地 diff 文件")
    r.add_argument("diff_file")
    r.add_argument("--llm", action="store_true", help="同时用 LLM 审查（需要 OPENAI_API_KEY）")
    r.add_argument("--json", action="store_true", help="只输出 JSON")

    pr = sub.add_parser("review-pr", help="审查 GitHub PR")
    pr.add_argument("--repo", required=True, help="owner/repo")
    pr.add_argument("--pr", required=True, type=int)
    pr.add_argument("--llm", action="store_true")
    pr.add_argument("--comment", action="store_true", help="把结果发到 PR 评论里")

    args = p.parse_args()

    if args.cmd == "review":
        text = open(args.diff_file, encoding="utf-8").read()
        findings = review_diff_text(text, use_llm=args.llm)
    else:
        text = get_pr_diff(args.repo, args.pr)
        findings = review_diff_text(text, use_llm=args.llm)
        if args.comment:
            # 需要 commit SHA，这里先用 PR 号占位，v2 再取最新 commit
            post_review_comment(args.repo, args.pr, "", findings)

    if args.json or args.cmd == "review-pr":
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("没有发现高置信度问题 ✅")
        for f in findings:
            print(f"[{f['severity']}] {f['file']}:{f.get('line')} {f['title']}")
            print(f"  {f['detail']}")
            print(f"  建议：{f['suggestion']}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
