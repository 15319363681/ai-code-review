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
    r.add_argument("--fix", action="store_true", help="为每个问题给出沙箱验证过的自动修复建议")
    r.add_argument("--no-cache", action="store_true", help="不使用增量缓存，全部重新审查")

    pr = sub.add_parser("review-pr", help="审查 GitHub PR")
    pr.add_argument("--repo", required=True, help="owner/repo")
    pr.add_argument("--pr", required=True, type=int)
    pr.add_argument("--llm", action="store_true")
    pr.add_argument("--fix", action="store_true", help="为每个问题给出沙箱验证过的自动修复建议")
    pr.add_argument("--no-cache", action="store_true", help="不使用增量缓存，全部重新审查")
    pr.add_argument("--comment", action="store_true", help="把结果发到 PR 评论里")

    args = p.parse_args()

    if args.cmd == "review":
        text = open(args.diff_file, encoding="utf-8").read()
        findings = review_diff_text(text, use_llm=args.llm, include_fixes=args.fix, use_cache=not args.no_cache)
    else:
        text = get_pr_diff(args.repo, args.pr)
        findings = review_diff_text(text, use_llm=args.llm, include_fixes=args.fix, use_cache=not args.no_cache)
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
            print(f"  建议：{f['suggestion']}")
            if f.get("fix"):
                status = "已验证" if f.get("fix_validated") else "未通过验证"
                print(f"  修复（{status}）：\n    " + f["fix"].replace("\n", "\n    "))
            print()
    sys.exit(0)


if __name__ == "__main__":
    main()
