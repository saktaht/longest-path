"""路線網の前処理：次数 2 の駅を「チェーン」に縮約する。

鉄道網の大半は分岐のない区間（次数 2 の駅の連なり）なので、
分岐駅（ジャンクション）だけを頂点に、区間（チェーン）を辺にしたグラフに縮約すると
探索対象の頂点数が大きく減る。縮約が最長経路を壊さない理由は README を参照。

用語:
- ジャンクション: 縮約後も頂点として残る駅（次数 != 2、自己ループを持つ、
  または全駅が次数 2 の閉路成分で代表に選ばれた駅）
- チェーン: ジャンクション a から次数 2 の駅（interior）を経てジャンクション b に至る区間。
  a == b のときはループチェーン
- 末端チェーン: 次数 3 以上のジャンクションから次数 1 の駅（終着駅）へ伸びるチェーン。
  経路の端でしか使えないので探索グラフから外し「しっぽ」として扱う
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set

from .parser import Edge


@dataclass
class Chain:
    a: int  # 端点の駅 ID
    b: int  # 端点の駅 ID（ループチェーンなら a と同じ）
    interior: List[int]  # a 側から b 側へ並んだ途中駅の ID
    weights: List[float]  # 各区間の距離（len(interior) + 1 個）
    total: float = field(init=False)

    def __post_init__(self) -> None:
        self.total = math.fsum(self.weights)

    @property
    def is_loop(self) -> bool:
        return self.a == self.b

    def interior_from(self, start: int) -> List[int]:
        """start 側から見た途中駅の並び。"""
        return list(self.interior) if start == self.a else list(reversed(self.interior))


@dataclass
class Network:
    chains: List[Chain]
    junctions: List[int]  # 探索グラフに残す駅 ID（末端チェーンの終着駅は含まない）
    leaf_chain_ids: Set[int]  # 末端チェーンの ID
    station_count: int


def build_network(edges: Sequence[Edge]) -> Network:
    adj: Dict[int, List[tuple]] = defaultdict(list)  # 駅 -> [(辺番号, 隣の駅)]
    degree: Dict[int, int] = defaultdict(int)
    self_loop: Set[int] = set()
    for i, e in enumerate(edges):
        if e.u == e.v:
            adj[e.u].append((i, e.u))
            degree[e.u] += 2
            self_loop.add(e.u)
        else:
            adj[e.u].append((i, e.v))
            adj[e.v].append((i, e.u))
            degree[e.u] += 1
            degree[e.v] += 1

    stations = sorted(adj)
    junction: Set[int] = {v for v in stations if degree[v] != 2 or v in self_loop}

    # 全駅が次数 2 の連結成分（単純な環状線）には、ID 最小の駅を代表ジャンクションとして置く
    seen: Set[int] = set()
    for v in stations:
        if v in seen:
            continue
        comp = [v]
        seen.add(v)
        k = 0
        while k < len(comp):
            for _, o in adj[comp[k]]:
                if o not in seen:
                    seen.add(o)
                    comp.append(o)
            k += 1
        if not any(x in junction for x in comp):
            junction.add(min(comp))

    used = [False] * len(edges)
    chains: List[Chain] = []
    for a in sorted(junction):
        for ei, other in adj[a]:
            if used[ei]:
                continue
            used[ei] = True
            interior: List[int] = []
            weights = [edges[ei].w]
            prev_e, cur = ei, other
            while cur not in junction:
                interior.append(cur)
                (e1, o1), (e2, o2) = adj[cur]  # 次数 2 かつ自己ループなし
                nxt_e, nxt = (e2, o2) if e1 == prev_e else (e1, o1)
                used[nxt_e] = True
                weights.append(edges[nxt_e].w)
                prev_e, cur = nxt_e, nxt
            chains.append(Chain(a, cur, interior, weights))

    # 次数 3 以上の駅から終着駅（次数 1）へ伸びるチェーンは末端チェーンとして探索グラフから外す
    leaf_chain_ids: Set[int] = set()
    removed: Set[int] = set()
    for cid, c in enumerate(chains):
        if c.is_loop:
            continue
        if degree[c.b] == 1 and degree[c.a] >= 3:
            leaf_chain_ids.add(cid)
            removed.add(c.b)
        elif degree[c.a] == 1 and degree[c.b] >= 3:
            # 向きをそろえて a を分岐駅側にする
            chains[cid] = Chain(c.b, c.a, list(reversed(c.interior)), list(reversed(c.weights)))
            leaf_chain_ids.add(cid)
            removed.add(c.a)

    return Network(
        chains=chains,
        junctions=sorted(junction - removed),
        leaf_chain_ids=leaf_chain_ids,
        station_count=len(stations),
    )
