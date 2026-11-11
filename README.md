# AI Code Review

一个能真正用起来的 AI 代码审查工具，不只是“读 PR diff、调 LLM”。

它会：拉取 PR diff → 解析变更 → 静态检查先过一遍 → 结合完整文件上下文让 LLM 做语义审查 → 去重、打分、过滤误报 → 在 PR 里逐行留评论。

## 为什么不只是读 diff

只看 diff 会漏掉很多东西：这个函数被谁调用、参数从哪来、有没有测试覆盖。
所以 v1 就做了三件事来解决这个难点：

1. **上下文补全**：不只看 diff 行，还会读完整文件、找调用方
2. **误报控制**：静态规则 + LLM 双通道，分级、去重、只报高置信度问题
3. **可评测**：输出结构化 JSON，方便以后拿真实 PR 做准确率 / 误报率评测

## 快速开始

```bash
pip install -r requirements.txt

# 本地审查一个 diff 文件（不需要 API Key 也能跑规则检查）
python -m ai_review.cli review examples/sample.diff

# 带自动修复建议（沙箱验证过才标已验证），第二次跑命中增量缓存
python -m ai_review.cli review examples/sample.diff --fix
python -m ai_review.cli review examples/sample.diff --no-cache  # 强制全量重审

# 接入 LLM（可选）
export OPENAI_API_KEY="sk-..."
python -m ai_review.cli review examples/sample.diff --llm

# 审查一个 GitHub PR
export GITHUB_TOKEN="ghp_..."
python -m ai_review.cli review-pr --repo owner/repo --pr 123 --llm
```

## 项目结构

```
src/ai_review/
  cli.py            # 命令行入口（--fix、--llm）
  diff_parser.py    # 解析 unified diff，按文件 / hunk 分组
  context.py        # v2：读完整文件，取改动行前后 20 行作上下文
  callgraph.py      # v3：ast 解析调用链，找改动函数的调用方
  autofix.py        # v3：自动修复建议，沙箱验证（py_compile）后才保留
  cache.py          # v4：按 hunk 哈希缓存审查结果，增量审查
  static_check.py   # 静态规则：安全、性能、风格（不用 LLM 也能跑）
  llm_reviewer.py   # LLM 审查：结构化输出，带上下文
  reviewer.py       # 编排：合并、去重、打分、过滤误报、接修复
  github_client.py  # GitHub API：拉 PR diff、发逐行评论
examples/
  sample.diff       # 示例 diff，里面埋了 3 个真问题
  clean.diff        # v4：干净 diff，应报 0 个问题
  eval_exec.diff    # v4：eval 执行任意代码
  sql_variant.diff  # v4：f-string 拼 SQL 注入
  read_file.diff    # v4：大文件一次性 read()
eval/
  run_eval.py       # v2：评测脚本，算召回率和误报数（v4：5 个 case）
tests/
  test_diff_parser.py
  test_static_check.py
  test_context.py   # v2：上下文补全测试
  test_callgraph.py # v3：调用链检索测试
  test_autofix.py   # v3：自动修复 + 沙箱验证测试
  test_cache.py     # v4：增量缓存测试
.github/workflows/
  code-review.yml   # GitHub Action：PR 一开就自动审查
```

## 输出示例

```json
{
  "file": "examples/sample.py",
  "line": 12,
  "severity": "high",
  "category": "security",
  "title": "SQL 拼接存在注入风险",
  "detail": "不要用字符串拼接拼 SQL，请用参数化查询。",
  "suggestion": "cursor.execute(\"SELECT * FROM users WHERE id = %s\", (user_id,))",
  "confidence": 0.92
}
```

## v2 已做（2026-11-09）

- **上下文补全**：`src/ai_review/context.py`，审查时自动读完整文件，取改动行前后 20 行一起发给 LLM，找不到文件时不编造、只用 diff 审
- **评测脚本**：`eval/run_eval.py`，用已知问题测召回率和误报数，当前示例集：召回率 100%（3/3），误报 0 个
  ```bash
  PYTHONPATH=src python3 eval/run_eval.py
  ```

## v3 已做（2026-11-10）

- **调用链检索**：`src/ai_review/callgraph.py`，用 ast 解析仓库里的 Python 文件，找出改动函数的调用方，把调用方文件、行号和代码片段一起发给 LLM；本地文件不存在时不编造调用方
- **自动修复 + 沙箱验证**：`src/ai_review/autofix.py`，对 SQL 注入（参数化查询）、硬编码密钥（`os.environ`）、空 except（记日志并 re-raise）、eval/exec（`ast.literal_eval`）给出具体修复片段；每个修复先在临时副本上 py_compile（真实文件）或 ast 解析（片段）验证，通过才在结果里标 `fix_validated: true`，绝不直接改用户代码
  ```bash
  PYTHONPATH=src python3 -m ai_review.cli review examples/sample.diff --fix
  ```

## v4 已做（2026-11-10）

- **增量审查 + 缓存**：`src/ai_review/cache.py`，按 diff hunk（文件 + hunk 内容）算 SHA256 哈希，结果存在 `.ai_review_cache.json`（已加入 `.gitignore`）；第二次跑没变过的 hunk 直接读缓存，变过的 hunk 才重新审查；`--no-cache` 可强制全量重审
  ```bash
  PYTHONPATH=src python3 -m ai_review.cli review examples/sample.diff          # 第一次算，写缓存
  PYTHONPATH=src python3 -m ai_review.cli review examples/sample.diff          # 第二次命中缓存
  PYTHONPATH=src python3 -m ai_review.cli review examples/sample.diff --no-cache
  ```
- **评测集扩大**：`examples/` 新增 clean.diff（应报 0 个）、eval_exec.diff（eval）、sql_variant.diff（f-string SQL 注入）、read_file.diff（大文件 read），`eval/run_eval.py` 按 case 汇报召回率和误报；总召回率 100%（6/6），误报 0 个
  ```bash
  PYTHONPATH=src python3 eval/run_eval.py
  ```

## 下一步

- [ ] 评测集：真实 PR 上的准确率 / 误报率

## 上传到 GitHub 的方法

1. 在 GitHub 网页新建仓库，名字比如 `ai-code-review`
2. 把这个文件夹里的全部文件拖进去上传，或用 git：
   ```bash
   git init
   git add .
   git commit -m "v2: context + eval"
   git remote add origin https://github.com/<你的用户名>/ai-code-review.git
   git push -u origin main
   ```
