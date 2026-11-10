"""评测脚本：用已知问题测准确率 / 误报。

用法：
    PYTHONPATH=src python3 eval/run_eval.py

评测集很小，但思路是对的：每个 case 都有已知应报的问题，
跑完算召回（找到了几个真问题）和误报数，写进 README 才有说服力。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

from ai_review.reviewer import review_diff_text

CASES = [
    {
        "name": "sample.diff 应报 3 个问题",
        "diff": Path("examples/sample.diff").read_text(encoding="utf-8"),
        "expected_titles": ["SQL 拼接存在注入风险", "疑似硬编码密钥", "空 except 会吞掉错误"],
    },
]


def main() -> int:
    total_expected = 0
    total_found = 0
    false_positives = 0
    for case in CASES:
        findings = review_diff_text(case["diff"], use_llm=False)
        titles = [f["title"] for f in findings]
        found = sum(1 for t in case["expected_titles"] if t in titles)
        fp = sum(1 for t in titles if t not in case["expected_titles"])
        total_expected += len(case["expected_titles"])
        total_found += found
        false_positives += fp
        print(f"{case['name']}: 找到 {found}/{len(case['expected_titles'])}，误报 {fp} 个")
        for f in findings:
            print(f"  - [{f['severity']}] {f['file']}:{f.get('line')} {f['title']}")
    recall = total_found / total_expected if total_expected else 0
    print(f"\n召回率：{recall:.0%}（{total_found}/{total_expected}），误报：{false_positives} 个")
    return 0 if recall == 1.0 and false_positives == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
