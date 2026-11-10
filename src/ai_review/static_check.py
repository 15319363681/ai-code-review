"""静态规则检查：不用 LLM 也能跑，先过滤掉确定性的问题。

思路：LLM 贵、慢、会幻觉；确定性的安全 / 性能问题先用规则扫一遍，
LLM 只负责需要语义理解的部分。这样既省成本，也能降低误报。
"""
from __future__ import annotations

import re

from .diff_parser import FileDiff

# 每条规则：(正则, 类别, 级别, 标题, 建议)
RULES = [
    (
        re.compile(r"execute\s*\(.*%.*\+|execute\s*\(f[\"'].*\{|SELECT.*\+|\+.*user_id"),
        "security",
        "high",
        "SQL 拼接存在注入风险",
        "不要用字符串拼接 / f-string 拼 SQL，请用参数化查询。",
    ),
    (
        re.compile(r"eval\s*\(|exec\s*\("),
        "security",
        "high",
        "eval / exec 执行任意代码",
        "避免 eval/exec，改用受限的解析或白名单分支。",
    ),
    (
        re.compile(r"password\s*=\s*[\"'][^\"']+[\"']|api_key\s*=\s*[\"'][^\"']+[\"']"),
        "security",
        "high",
        "疑似硬编码密钥",
        "密钥不要写进代码，用环境变量或密钥管理服务。",
    ),
    (
        re.compile(r"except\s*:\s*$|except\s+Exception\s*:\s*pass"),
        "bug",
        "medium",
        "空 except 会吞掉错误",
        "至少记日志，或只捕获你预期的具体异常。",
    ),
    (
        re.compile(r"open\s*\(.*\)\.read\(\)|read\(\)"),
        "performance",
        "low",
        "大文件请用流式读取",
        "大文件避免一次性 read()，考虑分块 / 逐行读。",
    ),
]


def check_file(diff: FileDiff) -> list[dict]:
    findings: list[dict] = []
    for line_no, content in diff.added_lines:
        for pattern, category, severity, title, suggestion in RULES:
            if pattern.search(content):
                findings.append(
                    {
                        "file": diff.path,
                        "line": line_no,
                        "severity": severity,
                        "category": category,
                        "title": title,
                        "detail": content.strip(),
                        "suggestion": suggestion,
                        "confidence": 0.95,
                        "source": "static",
                    }
                )
    return findings


def check_all(files: list[FileDiff]) -> list[dict]:
    out: list[dict] = []
    for f in files:
        out.extend(check_file(f))
    return out
