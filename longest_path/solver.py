"""最長片道きっぷ経路の探索（分枝限定法）。

縮約後のグラフ（ジャンクション＋チェーン）上で、各ジャンクションを始点とする深さ優先探索を行う。
探索の各ノードで

1. 「ここで終わる経路」（両端に“しっぽ”を付けたもの）を候補として評価
2. 「始点へ戻る閉路」を候補として評価
3. 上界を計算し、現在の最良値を超えられないなら枝刈り

を行う。上界と“しっぽ”の考え方は README を参照。
時間制限に達した場合はその時点の最良解を返し、``optimal=False`` とする。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, NamedTuple, Optional, Sequence, Tuple, Union

from .heuristic import heuristic_path
from .network import Network, build_network
from .parser import Edge

# 浮動小数点の丸め誤差で最適解を枝刈りしてしまわないよう、上界をわずかに膨らませる
_BOUND_REL_SLACK = 1e-12
_BOUND_ABS_SLACK = 1e-12
_TIME_CHECK_MASK = 0xFF  # 256 ノードごとに時刻を確認


@dataclass
class Result:
    route: List[int]  # 駅 ID の並び（閉路なら先頭の駅を末尾にも置く）
    length: float
    is_cycle: bool
    optimal: bool  # 探索を最後までやり切ったか
    interrupted: bool  # Ctrl+C で中断されたか
    junctions: int  # 縮約後の頂点数
    stations: int  # 元の駅数
    nodes: int  # 探索したノード数


# しっぽ: (伸ばせる距離, チェーン ID, ジャンクションから外へ向かう駅の並び)
Tail = Tuple[float, int, Tuple[int, ...]]


# 見つけた解の記録。経路の復元は探索の後にまとめて行う（route()）。
# どれもタプルなので、_offer での代入は 1 回で終わり、Ctrl+C で割り込まれても中途半端な状態にならない。
class _LoopRecord(NamedTuple):
    """ループチェーン 1 周だけの閉路。"""

    cid: int


class _PathRecord(NamedTuple):
    """ジャンクションの経路（チェーンは 0 本以上）の両端にしっぽを付けた経路。"""

    nodes: Tuple[int, ...]  # ジャンクション番号の並び
    chains: Tuple[int, ...]  # 隣り合うジャンクションを結ぶチェーン ID（len(nodes) - 1 個）
    tail_start: Optional[Tail]  # nodes[0] 側のしっぽ
    tail_end: Optional[Tail]  # nodes[-1] 側のしっぽ


class _CycleRecord(NamedTuple):
    """nodes を順にたどり、最後のチェーンで nodes[0] へ戻る閉路。"""

    nodes: Tuple[int, ...]
    chains: Tuple[int, ...]  # len(nodes) 個（最後が戻りのチェーン）


_Record = Union[_LoopRecord, _PathRecord, _CycleRecord]


class _Solver:
    def __init__(self, net: Network, time_limit: Optional[float], use_heuristic: bool) -> None:
        self.net = net
        self.use_heuristic = use_heuristic
        self.time_limit = time_limit
        self.deadline = None if time_limit is None else time.monotonic() + time_limit
        self.ids = net.junctions
        index = {v: i for i, v in enumerate(self.ids)}
        n = len(self.ids)

        # 探索グラフの隣接リスト: (距離, チェーン ID, 隣のジャンクション番号)、距離の降順
        self.jadj: List[List[Tuple[float, int, int]]] = [[] for _ in range(n)]
        # 各ジャンクションのしっぽ（チェーンごとに最良の 1 本、降順、上位 4 本）
        tails: List[dict] = [{} for _ in range(n)]
        self.loop_chain_ids: List[int] = []

        def add_tail(i: int, gain: float, cid: int, verts: Sequence[int]) -> None:
            if not verts:
                return
            old = tails[i].get(cid)
            if old is None or gain > old[0]:
                tails[i][cid] = (gain, cid, tuple(verts))

        for cid, c in enumerate(net.chains):
            a = index[c.a]
            if cid in net.leaf_chain_ids:
                add_tail(a, c.total, cid, c.interior + [c.b])
            elif c.is_loop:
                self.loop_chain_ids.append(cid)
                add_tail(a, c.total - c.weights[-1], cid, c.interior)
                add_tail(a, c.total - c.weights[0], cid, c.interior[::-1])
            else:
                b = index[c.b]
                self.jadj[a].append((c.total, cid, b))
                self.jadj[b].append((c.total, cid, a))
                add_tail(a, c.total - c.weights[-1], cid, c.interior)
                add_tail(b, c.total - c.weights[0], cid, c.interior[::-1])

        for lst in self.jadj:
            lst.sort(key=lambda t: -t[0])
        self.tails: List[List[Tail]] = [
            sorted(t.values(), key=lambda x: -x[0])[:4] for t in tails
        ]
        self.max_tail = [t[0][0] if t else 0.0 for t in self.tails]

        self.visited = [False] * n
        self.mark = [0] * n
        self.stamp = 0
        self.nodes = 0
        self.timed_out = False
        self.best_len = float("-inf")
        self.interrupted = False
        # (距離, 記録) を 1 つのタプルで持つ。Ctrl+C がどの行で割り込んでも距離と経路が食い違わない
        self.best: Optional[Tuple[float, _Record]] = None

    # ------------------------------------------------------------------ 候補

    def _offer(self, length: float, record: _Record) -> None:
        if length > self.best_len:
            self.best = (length, record)
            self.best_len = length

    def _best_tails(
        self, s: int, excl_s: Optional[int], h: int, excl_h: Optional[int]
    ) -> Tuple[float, Optional[Tail], Optional[Tail]]:
        """経路の両端 s, h に付けるしっぽの最良の組（同じチェーンは 2 度使わない）。"""
        ls = [t for t in self.tails[s] if t[1] != excl_s]
        lh = [t for t in self.tails[h] if t[1] != excl_h]
        if not ls and not lh:
            return 0.0, None, None
        best: Tuple[float, int, Optional[Tail], Optional[Tail]] = (-1.0, -1, None, None)
        for ts in [None] + ls[:3]:
            for th in [None] + lh[:3]:
                if ts is not None and th is not None and ts[1] == th[1]:
                    continue
                g = (ts[0] if ts else 0.0) + (th[0] if th else 0.0)
                cnt = (ts is not None) + (th is not None)
                if (g, cnt) > best[:2]:
                    best = (g, cnt, ts, th)
        return best[0], best[2], best[3]

    # ------------------------------------------------------------------ 上界

    def _bound(self, ends: Tuple[int, ...]) -> Tuple[float, float]:
        """経路の伸ばせる端 ends から、これ以上伸ばせる距離の上界（しっぽは含まない）。

        これから使う辺の集合 F について、各頂点に接続する F の辺の重みを合計すると
        2 * (F の総距離) になる。端 e は F の辺を高々 1 本（ends に同じ頂点が 2 回あれば 2 本）、
        未訪問の到達可能頂点 u は高々 2 本しか持たないので、それぞれ「接続する辺のうち
        重い順に 1 本 / 2 本」で抑えられる。端どうしを直接結ぶ辺（閉路を閉じる辺）も数える。
        戻り値: (上界, 到達可能範囲でのしっぽの最大値)
        """
        visited, jadj, mark = self.visited, self.jadj, self.mark
        self.stamp += 1
        st = self.stamp
        end_set = set(ends)
        total = 0.0
        queue: List[int] = []
        for e in ends:
            best1 = 0.0
            for w, _, j in jadj[e]:
                if not visited[j]:
                    if mark[j] != st:
                        mark[j] = st
                        queue.append(j)
                elif j == e or j not in end_set:
                    continue
                if w > best1:
                    best1 = w
            total += best1
        max_tail = self.max_tail
        mt = max(max_tail[e] for e in ends)
        k = 0
        while k < len(queue):
            u = queue[k]
            k += 1
            a1 = a2 = 0.0
            for w, _, j in jadj[u]:
                if not visited[j]:
                    if mark[j] != st:
                        mark[j] = st
                        queue.append(j)
                elif j not in end_set:
                    continue
                if w > a1:
                    a1, a2 = w, a1
                elif w > a2:
                    a2 = w
            total += a1 + a2
            if max_tail[u] > mt:
                mt = max_tail[u]
        return total / 2.0, mt

    def _can_improve(self, upper: float) -> bool:
        return upper * (1 + _BOUND_REL_SLACK) + _BOUND_ABS_SLACK > self.best_len

    def _tick(self) -> bool:
        """ノード数を数え、時間切れなら True。"""
        self.nodes += 1
        if (
            self.deadline is not None
            and (self.nodes & _TIME_CHECK_MASK) == 0
            and time.monotonic() > self.deadline
        ):
            self.timed_out = True
        return self.timed_out

    # ------------------------------------------------------------------ 探索
    #
    # 対称性の除去: 経路・閉路は「その上で探索順位が最も高いジャンクション s」からだけ探す。
    # s の探索が終わったら s は二度と使わない（visited のまま残す）ので、後の探索ほどグラフが小さい。
    # s が経路の途中にある場合に備え、s から前方（front）に伸ばしたあと、
    # 後方（back）にも伸ばす 2 段階の探索をする。
    # 同じ経路を向きを変えて 2 回見つけないよう、back の最初のチェーン ID は front の最初より大きくする。

    def _visit_front(self, s: int, fpath: List[int], fch: List[int], cur: float) -> bool:
        """front 側の端 h = fpath[-1] に到達したときの処理。子を展開すべきなら True。"""
        if self._tick():
            return False
        h = fpath[-1]
        # 1. s と h を両端とする経路
        g, ts, th = self._best_tails(s, fch[0] if fch else None, h, fch[-1] if fch else None)
        if (fch or ts is not None or th is not None) and cur + g > self.best_len:
            self._offer(cur + g, _PathRecord(tuple(fpath), tuple(fch), ts, th))
        # 2. s へ戻る閉路（来たのと別のチェーンで戻る）
        if fch:
            first = fch[0]
            for w, cid, j in self.jadj[h]:
                if j == s and cid != first and cur + w > self.best_len:
                    self._offer(cur + w, _CycleRecord(tuple(fpath), tuple(fch) + (cid,)))
        # 3. 枝刈り（front も back もまだ伸ばせる。根では s から 2 方向に伸ばせる）
        ub, mt = self._bound((h, s) if fch else (s, s))
        return self._can_improve(cur + ub + 2 * mt)

    def _visit_back(
        self, fpath: List[int], fch: List[int], bpath: List[int], bch: List[int], cur: float
    ) -> bool:
        """back 側の端 b = bpath[-1] に到達したときの処理。front 側の端 h は固定。"""
        if self._tick():
            return False
        h, b = fpath[-1], bpath[-1]
        g, tb, th = self._best_tails(b, bch[-1], h, fch[-1])
        if cur + g > self.best_len:
            nodes = tuple(reversed(bpath)) + tuple(fpath)
            chains = tuple(reversed(bch)) + tuple(fch)
            self._offer(cur + g, _PathRecord(nodes, chains, tb, th))
        ub, mt = self._bound((b,))
        return self._can_improve(cur + ub + mt + self.max_tail[h])

    def _search_from(self, s: int) -> None:
        visited, jadj = self.visited, self.jadj
        fpath, fch, flen = [s], [], [0.0]  # front 側: s から伸ばした駅・チェーン・累積距離
        bpath, bch, blen = [], [], [0.0]  # back 側: s の反対側に伸ばした分
        visited[s] = True
        FRONT, BACK_ROOT, BACK = 0, 1, 2
        frames: List[List[int]] = []  # [種類, 端の駅, 次に調べる隣接リストの位置]
        if self._visit_front(s, fpath, fch, 0.0):
            frames.append([FRONT, s, 0])
        while frames and not self.timed_out:
            fr = frames[-1]
            kind, h, i = fr
            nbrs = jadj[h]
            pushed = False
            while i < len(nbrs) and not self.timed_out:
                w, cid, j = nbrs[i]
                i += 1
                if visited[j] or (kind == BACK_ROOT and cid <= fch[0]):
                    continue
                visited[j] = True
                if kind == FRONT:
                    fpath.append(j)
                    fch.append(cid)
                    flen.append(flen[-1] + w)
                    ok = self._visit_front(s, fpath, fch, flen[-1] + blen[-1])
                else:
                    bpath.append(j)
                    bch.append(cid)
                    blen.append(blen[-1] + w)
                    ok = self._visit_back(fpath, fch, bpath, bch, flen[-1] + blen[-1])
                if ok:
                    fr[2] = i
                    frames.append([FRONT if kind == FRONT else BACK, j, 0])
                    pushed = True
                    break
                visited[j] = False
                if kind == FRONT:
                    fpath.pop(), fch.pop(), flen.pop()
                else:
                    bpath.pop(), bch.pop(), blen.pop()
            if pushed or self.timed_out:
                continue
            if kind == FRONT and h != s and i == len(nbrs):
                # front を h で止め、s の反対側（back）へ伸ばす探索に移る
                fr[2] = i + 1
                ub, mt = self._bound((s,))
                if self._can_improve(flen[-1] + ub + mt + self.max_tail[h]):
                    frames.append([BACK_ROOT, s, 0])
                    continue
            frames.pop()
            if kind == FRONT and h != s:
                visited[h] = False
                fpath.pop(), fch.pop(), flen.pop()
            elif kind == BACK:
                visited[h] = False
                bpath.pop(), bch.pop(), blen.pop()
        if self.timed_out:
            for v in fpath + bpath:
                visited[v] = False
        # 探索をやり切った s は visited のまま残し、以降の探索から除外する

    def run(self) -> None:
        """探索する。Ctrl+C で中断されたら、その時点の最良解を残して戻る。"""
        try:
            self._run()
        except KeyboardInterrupt:
            self.interrupted = True

    def _offer_simple_candidates(self) -> None:
        """ループチェーン 1 周と、チェーン 0〜1 本＋しっぽの経路を候補にする。

        どれもすぐ求まる。ヒューリスティックの最中に Ctrl+C されても、出力する経路が残るようにするため。
        """
        for cid in self.loop_chain_ids:
            self._offer(self.net.chains[cid].total, _LoopRecord(cid))
        for a, lst in enumerate(self.jadj):
            g, ts, th = self._best_tails(a, None, a, None)
            if ts is not None or th is not None:
                self._offer(g, _PathRecord((a,), (), ts, th))
            for w, cid, b in lst:
                if a < b:  # 各チェーンは両端の隣接リストに 1 回ずつ現れるので、片方だけ見る
                    g, ts, th = self._best_tails(a, cid, b, cid)
                    self._offer(w + g, _PathRecord((a, b), (cid,), ts, th))

    def _run(self) -> None:
        self._offer_simple_candidates()

        # 初期解: 最大 1 秒（時間制限があればその 1 割まで）をヒューリスティックに使う
        budget = 1.0 if self.time_limit is None else min(1.0, self.time_limit * 0.1)
        found = heuristic_path(self.jadj, budget) if self.use_heuristic else None
        if found is not None:
            nodes, chains, length = found
            g, ts, th = self._best_tails(nodes[0], chains[0], nodes[-1], chains[-1])
            self._offer(length + g, _PathRecord(tuple(nodes), tuple(chains), ts, th))

        # 分岐の多い・重い駅から順に始点にする（早く除外するほど後の探索が軽くなる）
        def potential(i: int) -> Tuple[int, float]:
            return (len(self.jadj[i]), sum(w for w, _, _ in self.jadj[i]) + self.max_tail[i])

        for s in sorted(range(len(self.ids)), key=potential, reverse=True):
            if self.timed_out:
                break
            self._search_from(s)

    # ------------------------------------------------------------------ 復元

    def route(self) -> Tuple[List[int], bool]:
        if self.best is None:
            return [], False
        chains = self.net.chains
        rec = self.best[1]
        if isinstance(rec, _LoopRecord):
            c = chains[rec.cid]
            return [c.a] + c.interior + [c.a], True
        is_cycle = isinstance(rec, _CycleRecord)
        nodes = list(rec.nodes) + ([rec.nodes[0]] if is_cycle else [])
        out = [self.ids[nodes[0]]]
        for k, cid in enumerate(rec.chains):
            x, y = self.ids[nodes[k]], self.ids[nodes[k + 1]]
            out += chains[cid].interior_from(x)
            out.append(y)
        if isinstance(rec, _CycleRecord):
            return out, True
        if rec.tail_start is not None:
            out = list(reversed(rec.tail_start[2])) + out
        if rec.tail_end is not None:
            out = out + list(rec.tail_end[2])
        return out, False


def _normalize(route: List[int], is_cycle: bool) -> List[int]:
    """出力を決定的にする: 閉路は最小 ID から小さい隣へ、経路は ID の小さい端から。"""
    if not route:
        return route
    if is_cycle:
        body = route[:-1]
        k = body.index(min(body))
        body = body[k:] + body[:k]
        if len(body) > 2 and body[-1] < body[1]:
            body = [body[0]] + body[:0:-1]
        return body + [body[0]]
    return route if route[0] <= route[-1] else route[::-1]


def solve(
    edges: Sequence[Edge], time_limit: Optional[float] = None, use_heuristic: bool = True
) -> Result:
    """最長経路を求める。time_limit 秒（None なら無制限）で打ち切り、その時点の最良解を返す。

    Ctrl+C で中断されたら、その時点の最良解を ``interrupted=True`` で返す
    （前処理の途中なら経路は空）。
    """
    try:
        net = build_network(edges)
        solver = _Solver(net, time_limit, use_heuristic)
    except KeyboardInterrupt:
        return Result(
            route=[], length=0.0, is_cycle=False, optimal=False, interrupted=True,
            junctions=0, stations=0, nodes=0,
        )
    solver.run()
    route, is_cycle = solver.route()
    return Result(
        route=_normalize(route, is_cycle),
        length=solver.best[0] if solver.best is not None else 0.0,
        is_cycle=is_cycle,
        optimal=not (solver.timed_out or solver.interrupted),
        interrupted=solver.interrupted,
        junctions=len(net.junctions),
        stations=net.station_count,
        nodes=solver.nodes,
    )
