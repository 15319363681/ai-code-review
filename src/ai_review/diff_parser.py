"""解析 unified diff，按文件 / hunk 分组，保留新文件行号。

只读 diff 是入门版的瓶颈：diff 里只有改动行，不知道完整上下文。
这个模块是第一步，先把 diff 结构化，后面 reviewer 再去补完整文件。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hunk:
    old_start: int
    new_start: int
    lines: list[str] = field(default_factory=list)  # 带 +/- / 空格前缀的原始行
    added_lines: list[tuple[int, str]] = field(default_factory=list)  # (新行号, 内容)


@dataclass
class FileDiff:
    path: str
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def added_lines(self) -> list[tuple[int, str]]:
        out: list[tuple[int, str]] = []
        for h in self.hunks:
            out.extend(h.added_lines)
        return out


def parse_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    hunk: Hunk | None = None
    new_line_no = 0

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("+++ b/"):
            path = line[6:]
            current = FileDiff(path=path)
            files.append(current)
            hunk = None
        elif line.startswith("@@ "):
            # @@ -12,7 +12,9 @@
            try:
                parts = line.split(" ")
                new_part = [p for p in parts if p.startswith("+")][0]
                new_start = int(new_part[1:].split(",")[0])
            except Exception:
                new_start = 0
            hunk = Hunk(old_start=0, new_start=new_start)
            if current is not None:
                current.hunks.append(hunk)
            new_line_no = new_start
        elif hunk is not None and current is not None:
            if line.startswith("+") and not line.startswith("+++"):
                hunk.lines.append(line)
                hunk.added_lines.append((new_line_no, line[1:]))
                new_line_no += 1
            elif line.startswith("-") and not line.startswith("---"):
                hunk.lines.append(line)
            else:
                hunk.lines.append(line)
                new_line_no += 1
    return files
