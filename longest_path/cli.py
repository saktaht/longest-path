"""コマンドラインのエントリポイント。

標準入力から路線網を読み、最長経路の駅 ID を \r\n 区切りで標準出力に書く。
補足情報（総距離・最適性・警告）は標準エラー出力へ出し、標準出力は答えだけにする。
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import List, Optional

from .parser import parse_edges
from .solver import solve

_EXIT_INTERRUPTED = 130  # SIGINT で終わったときの慣例的な終了コード


def _time_limit(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if math.isnan(value) or value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0 (0 = no limit): {text!r}")
    return value


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m longest_path",
        description="標準入力の路線網から最長片道きっぷの経路を求める",
    )
    p.add_argument(
        "-t",
        "--time-limit",
        type=_time_limit,
        default=0.0,
        help="探索の時間制限（秒、0 以上）。既定は 0（無制限）。時間切れのときはその時点の最良解を出力する",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="総距離や探索統計を標準エラー出力に表示する"
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    started = time.monotonic()
    try:
        # Windows でも \r\n が \r\r\n にならないよう、入出力はバイト列で扱う
        text = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        edges, warnings = parse_edges(text)
    except KeyboardInterrupt:
        print("interrupted while reading the input", file=sys.stderr)
        return _EXIT_INTERRUPTED
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    # 探索中・前処理中の Ctrl+C は solve() が受け止めて、その時点の最良解を返す
    limit = args.time_limit if args.time_limit > 0 else None
    result = solve(edges, time_limit=limit)

    out = "".join(f"{v}\r\n" for v in result.route)
    sys.stdout.buffer.write(out.encode("ascii"))
    sys.stdout.buffer.flush()

    if result.interrupted:
        if not result.route:
            print("warning: interrupted (Ctrl+C) before any route was found", file=sys.stderr)
            return _EXIT_INTERRUPTED
        print(
            "warning: interrupted (Ctrl+C); "
            "printed the best route found so far (optimality not proven)",
            file=sys.stderr,
        )
    elif not result.optimal:
        print(
            f"warning: time limit ({args.time_limit:g}s) reached; "
            "printed the best route found so far (optimality not proven)",
            file=sys.stderr,
        )
    if args.verbose:
        kind = "cycle" if result.is_cycle else "path"
        print(
            f"length={result.length:.6f} kind={kind} stations_on_route="
            f"{len(result.route) - (1 if result.is_cycle else 0)} optimal={result.optimal}\n"
            f"stations={result.stations} junctions_after_contraction={result.junctions} "
            f"search_nodes={result.nodes} elapsed={time.monotonic() - started:.3f}s",
            file=sys.stderr,
        )
    return 0
