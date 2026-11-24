"""ブロックカット木版の上界と、本体の上界の速度比較。

block_bound.patch を当てた状態で、リポジトリ直下から実行する:
    git apply experiments/block_cut_tree/block_bound.patch
    python3 experiments/block_cut_tree/bench.py
    git apply -R experiments/block_cut_tree/block_bound.patch   # 元に戻す
"""
import subprocess, sys, time
sys.path.insert(0, ".")
from longest_path import parse_edges, solve
cases = [
    ("random", "--nodes 25 --edges 50", 1), ("random", "--nodes 25 --edges 50", 2),
    ("random", "--nodes 30 --edges 60", 1), ("random", "--nodes 30 --edges 60", 2),
    ("railway", "--hubs 49", 1), ("railway", "--hubs 49", 2),
    ("railway", "--hubs 64", 1), ("railway", "--hubs 64", 2),
    ("railway", "--hubs 81", 1), ("railway", "--hubs 81", 2),
    ("railway", "--hubs 100", 1),
]
LIMIT = 90
for kind, args, seed in cases:
    txt = subprocess.run([sys.executable, "tools/gen_graph.py", kind, *args.split(), "--seed", str(seed)], capture_output=True, text=True).stdout
    edges, _ = parse_edges(txt)
    row = []
    for bb in (False, True):
        t = time.monotonic(); r = solve(edges, time_limit=LIMIT, use_block_bound=bb); dt = time.monotonic() - t
        row.append(f"{dt:7.2f}s {'opt ' if r.optimal else 'TIME'} nodes={r.nodes:>9} len={r.length:.1f}")
    print(f"{kind:7} {args:22} seed={seed} J={r.junctions:3} | old: {row[0]} | block: {row[1]}", flush=True)
