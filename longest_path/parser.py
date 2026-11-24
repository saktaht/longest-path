"""標準入力のテキストを辺のリストに変換する。

フォーマット: ``始点ID, 終点ID, 距離\\r\\n``
- ID は正の整数、距離は 0 以上の有限な浮動小数点数
- 数値の前後には任意個の空白・タブが入りうる
- 改行は \\r\\n / \\n のどちらでも受け付ける
- 形式に合わない行は捨てて警告を返す（処理全体は止めない）
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Tuple

_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_LINE = re.compile(
    r"^[ \t]*(\d+)[ \t]*,[ \t]*(\d+)[ \t]*,[ \t]*(" + _NUMBER + r")[ \t]*$",
    re.ASCII,  # \d を 0-9 だけにする（Unicode の数字は受け付けない）
)


@dataclass(frozen=True)
class Edge:
    u: int
    v: int
    w: float


def parse_edges(text: str) -> Tuple[List[Edge], List[str]]:
    """テキストを解析して (辺のリスト, 警告メッセージのリスト) を返す。"""
    edges: List[Edge] = []
    warnings: List[str] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        m = _LINE.match(raw)
        if m is None:
            warnings.append(f"line {lineno}: invalid format, skipped: {raw!r}")
            continue
        u, v, w = int(m.group(1)), int(m.group(2)), float(m.group(3))
        if u <= 0 or v <= 0:
            warnings.append(f"line {lineno}: station ID must be positive, skipped: {raw!r}")
            continue
        if not math.isfinite(w) or w < 0:
            warnings.append(f"line {lineno}: distance must be finite and >= 0, skipped: {raw!r}")
            continue
        edges.append(Edge(u, v, w))
    return edges, warnings
