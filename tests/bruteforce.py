"""テスト用の素朴な総当たり解法と、出力経路の検証器。

縮約などの工夫を一切せず元のグラフ上で全単純経路・全閉路を列挙する。
小さいグラフでしか動かないが、本体の正しさを確かめる基準として使う。
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Dict, List, Sequence

from longest_path import Edge


def brute_force(edges: Sequence[Edge]) -> float:
    adj: Dict[int, List[tuple]] = defaultdict(list)
    best = 0.0
    for i, e in enumerate(edges):
        if e.u == e.v:
            best = max(best, e.w)  # 自己ループだけの閉路
            continue
        adj[e.u].append((i, e.v, e.w))
        adj[e.v].append((i, e.u, e.w))

    def dfs(s: int, h: int, first_edge: int, length: float, visited: set) -> None:
        nonlocal best
        best = max(best, length)
        for ei, j, w in adj[h]:
            if j == s and first_edge != -1 and ei != first_edge:
                best = max(best, length + w)  # 閉路
            if j not in visited:
                visited.add(j)
                dfs(s, j, ei if first_edge == -1 else first_edge, length + w, visited)
                visited.discard(j)

    for s in list(adj):
        dfs(s, s, -1, 0.0, {s})
    return best


def route_length(edges: Sequence[Edge], route: List[int]) -> float:
    """出力された駅の並びが正しい旅程か検証し、取りうる最大の距離を返す。"""
    if not route:
        return 0.0
    assert len(route) >= 2, "route must contain at least one edge"
    is_cycle = route[0] == route[-1]
    body = route[:-1] if is_cycle else route
    assert len(set(body)) == len(body), f"station visited twice: {route}"

    weights: Dict[frozenset, List[float]] = defaultdict(list)
    for e in edges:
        weights[frozenset((e.u, e.v))].append(e.w)
    for k in weights:
        weights[k].sort(reverse=True)

    if is_cycle and len(body) == 2:  # 平行な 2 本の辺による閉路
        ws = weights[frozenset(body)]
        assert len(ws) >= 2, f"2-cycle needs parallel edges: {route}"
        return ws[0] + ws[1]
    total = []
    for x, y in zip(route, route[1:]):
        ws = weights.get(frozenset((x, y)))
        assert ws, f"no edge between {x} and {y}"
        total.append(ws[0])
    return math.fsum(total)
