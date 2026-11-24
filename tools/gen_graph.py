"""ベンチマーク用の入力生成スクリプト。

使い方:
    python tools/gen_graph.py random  --nodes 30 --edges 60 --seed 1 > in.txt
    python tools/gen_graph.py railway --hubs 40 --seed 1 > in.txt

random  : 一様ランダムな連結グラフ（最悪寄りのケース）
railway : 鉄道網に似せたグラフ。格子状に置いた分岐駅を途中駅入りの区間で結び、
          一部の区間を間引き、終着駅への支線を生やす
"""

from __future__ import annotations

import argparse
import random
import sys


def gen_random(nodes: int, edges: int, rng: random.Random):
    out = []
    order = list(range(1, nodes + 1))
    rng.shuffle(order)
    for i in range(1, nodes):  # まず全域木で連結にする
        out.append((order[i], order[rng.randrange(i)]))
    pairs = {frozenset(p) for p in out}
    while len(out) < edges and len(pairs) < nodes * (nodes - 1) // 2:
        u, v = rng.sample(range(1, nodes + 1), 2)
        if frozenset((u, v)) not in pairs:
            pairs.add(frozenset((u, v)))
            out.append((u, v))
    return [(u, v, round(rng.uniform(1, 100), 2)) for u, v in out]


def gen_railway(hubs: int, rng: random.Random):
    side = max(2, int(hubs ** 0.5))
    hub_ids = list(range(1, side * side + 1))
    nxt = len(hub_ids) + 1
    out = []

    def link(a, b):
        nonlocal nxt
        prev = a
        for _ in range(rng.randint(0, 6)):
            out.append((prev, nxt, round(rng.uniform(0.5, 8), 1)))
            prev, nxt = nxt, nxt + 1
        out.append((prev, b, round(rng.uniform(0.5, 8), 1)))

    for r in range(side):
        for c in range(side):
            h = r * side + c + 1
            if c + 1 < side and rng.random() < 0.8:
                link(h, h + 1)
            if r + 1 < side and rng.random() < 0.8:
                link(h, h + side)
    for _ in range(side):
        prev = rng.choice(hub_ids)
        for _ in range(rng.randint(1, 8)):
            out.append((prev, nxt, round(rng.uniform(0.5, 8), 1)))
            prev, nxt = nxt, nxt + 1
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["random", "railway"])
    p.add_argument("--nodes", type=int, default=30)
    p.add_argument("--edges", type=int, default=60)
    p.add_argument("--hubs", type=int, default=36)
    p.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    rng = random.Random(a.seed)
    rows = gen_random(a.nodes, a.edges, rng) if a.kind == "random" else gen_railway(a.hubs, rng)
    sys.stdout.buffer.write("".join(f"{u}, {v}, {w}\r\n" for u, v, w in rows).encode())


if __name__ == "__main__":
    main()
