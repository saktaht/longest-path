"""厳密探索の前に、そこそこ長い経路を素早く作るヒューリスティック。

目的は 2 つ:
- 分枝限定法の初期解（暫定最良値）を良くして、序盤から枝刈りを効かせる
- 大きな入力で時間切れになっても、質の良い経路を出力できるようにする

方法: 貪欲に両端を伸ばした経路を作り、次の 2 種類の改善を、改善がなくなるまで繰り返す。
- 迂回の挿入: 経路上の隣り合う a-b を、未使用の駅を通る a-x-…-b に置き換えて長くなるなら置き換える
- 端の延長: 経路の端から未使用の駅へ浅い深さ優先探索で伸ばす
始点を変えて何度か繰り返し、最良のものを返す。乱数の種は固定なので結果は再現する。

浅い探索 1 回でも、次数の大きいグラフでは時間がかかる（次数の 5 乗程度）。
そこで探索の途中でも一定回数ごとに時刻を確かめ、持ち時間を過ぎたらそこで打ち切る。
"""

from __future__ import annotations

import random
import time
from typing import List, Optional, Sequence, Tuple

Adj = Sequence[Sequence[Tuple[float, int, int]]]  # (距離, チェーン ID, 隣の頂点)

_DETOUR_DEPTH = 5  # 迂回・延長で調べる深さ（チェーン数）
_TIME_CHECK_MASK = 0x3FF  # 浅い探索の 1024 ステップごとに時刻を確認


class _OutOfTime(Exception):
    """ヒューリスティックの持ち時間を使い切った。"""


class _Path:
    def __init__(self, adj: Adj, start: int, deadline: float) -> None:
        self.adj = adj
        self.deadline = deadline
        self.nodes = [start]
        self.chains: List[int] = []
        self.weights: List[float] = []
        self.used = {start}
        self._steps = 0

    @property
    def length(self) -> float:
        return sum(self.weights)

    def _best_walk(self, start: int, depth: int, goal: Optional[int]) -> Tuple[float, list]:
        """start から未使用の駅を通る深さ depth 以内の歩みのうち最長のもの。
        goal が指定されたら goal で終わるものに限る。戻り値: (距離, [(w, cid, v), ...])

        持ち時間を過ぎたら _OutOfTime を送出する。そのとき self.used は呼び出し前の状態に戻す。"""
        best: Tuple[float, list] = (float("-inf"), [])
        stack: list = []
        seen = self.used

        def dfs(v: int, length: float) -> None:
            nonlocal best
            self._steps += 1
            if (self._steps & _TIME_CHECK_MASK) == 0 and time.monotonic() >= self.deadline:
                raise _OutOfTime
            if goal is None and stack and length > best[0]:
                best = (length, list(stack))
            if len(stack) >= depth:
                return
            for w, cid, j in self.adj[v]:
                if goal is not None and j == goal and stack:
                    if length + w > best[0]:
                        best = (length + w, stack + [(w, cid, j)])
                    continue
                if j in seen:
                    continue
                seen.add(j)
                stack.append((w, cid, j))
                dfs(j, length + w)
                stack.pop()
                seen.discard(j)

        try:
            dfs(start, 0.0)
        except _OutOfTime:
            # 探索中に一時的に足した駅（stack に積んだもの）を used から外してから伝える
            for _, _, j in stack:
                seen.discard(j)
            raise
        return best

    def improve_once(self) -> bool:
        # 端の延長（後ろ側、向きを反転して前側）
        for _ in range(2):
            gain, walk = self._best_walk(self.nodes[-1], _DETOUR_DEPTH, None)
            if walk:
                for w, cid, j in walk:
                    self.nodes.append(j)
                    self.chains.append(cid)
                    self.weights.append(w)
                    self.used.add(j)
                return True
            self.nodes.reverse()
            self.chains.reverse()
            self.weights.reverse()
        # 迂回の挿入
        for i in range(len(self.chains)):
            a, b, w0 = self.nodes[i], self.nodes[i + 1], self.weights[i]
            gain, walk = self._best_walk(a, _DETOUR_DEPTH, b)
            if walk and gain > w0:
                mid = walk[:-1]
                self.nodes[i + 1 : i + 1] = [j for _, _, j in mid]
                self.chains[i : i + 1] = [cid for _, cid, _ in walk]
                self.weights[i : i + 1] = [w for w, _, _ in walk]
                self.used.update(j for _, _, j in mid)
                return True
        return False


def heuristic_path(
    adj: Adj, budget_sec: float, restarts: int = 32, seed: int = 2028
) -> Optional[Tuple[List[int], List[int], float]]:
    """(頂点列, チェーン列, 距離) を返す。辺がないか、持ち時間内に 1 本も作れなければ None。"""
    n = len(adj)
    candidates = [v for v in range(n) if adj[v]]
    if not candidates:
        return None
    rng = random.Random(seed)
    deadline = time.monotonic() + budget_sec
    # 次数の大きい駅を優先しつつ、残りはランダムに始点を選ぶ
    starts = sorted(candidates, key=lambda v: -len(adj[v]))[: max(1, restarts // 2)]
    starts += [rng.choice(candidates) for _ in range(restarts - len(starts))]

    best: Optional[_Path] = None
    for s in starts:
        p = _Path(adj, s, deadline)
        try:
            while time.monotonic() < deadline and p.improve_once():
                pass
        except _OutOfTime:
            pass  # improve_once は探索が終わってから経路を書き換えるので、p は正しい経路のまま
        # 時間切れで一度も伸ばせなかった経路（辺が 0 本）は候補にしない
        if p.chains and (best is None or p.length > best.length):
            best = p
        if time.monotonic() >= deadline:
            break
    if best is None:
        return None
    return best.nodes, best.chains, best.length
