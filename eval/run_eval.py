"""评测脚本：用已知问题测准确率 / 误报。

用法：
    PYTHONPATH=src python3 eval/run_eval.py

评测集：每个 case 都有已知应报的问题（clean.diff 应报 0 个），
跑完按 case 算召回和误报，再汇总写进 README 才有说服力。
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

from ai_review.reviewer import review_diff_text

CASES = [
    {
        "name": "sample.diff 应报 3 个问题",
        "diff": (BASE / "examples" / "sample.diff").read_text(encoding="utf-8"),
        "expected_titles": ["SQL 拼接存在注入风险", "疑似硬编码密钥", "空 except 会吞掉错误"],
    },
    {
        "name": "clean.diff 应报 0 个问题",
        "diff": (BASE / "examples" / "clean.diff").read_text(encoding="utf-8"),
        "expected_titles": [],
    },
    {
        "name": "eval_exec.diff应报 eval/exec",
        "diff": (BASE / "examples" / "eval_exec.diff").read_text(encoding="utf-8"),
        "expected_titles": ["eval / exec 执行任意代码"],
    },
    {
        "name": "sql_variant.diff应报 f-string SQL 注入",
        "diff": (BASE / "examples" / "sql_variant.diff").read_text(encoding="utf-8"),
        "expected_titles": ["SQL 拼接存在注入风险"],
    },
    {
        "name": "read_file.diff应报大文件流式读取",
        "diff": (BASE / "examples" / "read_file.diff").read_text(encoding="utf-8"),
        "expected_titles": ["大文件请用流式读取"],
    },
]


def main() -> int:
    total_expected = 0
    total_found = 0
    false_positives = 0
    for case in CASES:
        findings = review_diff_text(case["diff"], use_llm=False, use_cache=False)
        titles = [f["title"] for f in findings]
        found = sum(1 for t in case["expected_titles"] if t in titles)
        fp = sum(1 for t in titles if t not in case["expected_titles"])
        total_expected += len(case["expected_titles"])
        total_found += found
        false_positives += fp
        recall = found / len(case["expected_titles"]) if case["expected_titles"] else 1.0
        print(f"{case['name']}: 召回 {recall:.0%}（{found}/{len(case['expected_titles'])}），误报 {fp} 个")
        for f in findings:
            print(f"  - [{f['severity']}] {f['file']}:{f.get('line')} {f['title']}")
    recall = total_found / total_expected if total_expected else 0
    print(f"\n总召回率：{recall:.0%}（{total_found}/{total_expected}），总误报：{false_positives} 个")
    return 0 if recall == 1.0 and false_positives == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
