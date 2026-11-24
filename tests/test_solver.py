import random
import time
import unittest
from unittest import mock

from longest_path import Edge, solve
from tests.bruteforce import brute_force, route_length


def E(*triples):
    return [Edge(u, v, float(w)) for u, v, w in triples]


class SolverExamples(unittest.TestCase):
    def check(self, edges, expected_length, expected_route=None):
        r = solve(edges, use_heuristic=False)
        self.assertTrue(r.optimal)
        self.assertAlmostEqual(r.length, expected_length, places=9)
        self.assertAlmostEqual(route_length(edges, r.route), expected_length, places=9)
        if expected_route is not None:
            self.assertEqual(r.route, expected_route)
        return r

    def test_problem_sample(self):
        edges = E((1, 2, 8.54), (2, 3, 3.11), (3, 1, 2.19), (3, 4, 4), (4, 1, 1.4))
        r = self.check(edges, 17.05, [1, 2, 3, 4, 1])
        self.assertTrue(r.is_cycle)

    def test_empty(self):
        r = solve([])
        self.assertEqual(r.route, [])

    def test_single_edge(self):
        self.check(E((5, 3, 2.5)), 2.5, [3, 5])

    def test_simple_line(self):
        self.check(E((1, 2, 1), (2, 3, 2), (3, 4, 3)), 6, [1, 2, 3, 4])

    def test_ring_only(self):
        # 全駅が次数 2 の環状線
        self.check(E((1, 2, 1), (2, 3, 1), (3, 4, 1), (4, 1, 1)), 4, [1, 2, 3, 4, 1])

    def test_star_uses_two_longest_branches(self):
        self.check(E((1, 2, 5), (1, 3, 1), (1, 4, 7), (4, 5, 1)), 13, [2, 1, 4, 5])

    def test_path_ends_inside_chain(self):
        # 1-2-3-4-1 の環に、4 から 10 への長い枝。最長は 10 から入って環をほぼ一周し途中駅で終わる
        edges = E((1, 2, 1), (2, 3, 1), (3, 4, 1), (4, 1, 1), (4, 10, 100))
        self.check(edges, 103)

    def test_parallel_edges_form_cycle(self):
        self.check(E((1, 2, 3), (1, 2, 4)), 7, [1, 2, 1])

    def test_self_loop(self):
        self.check(E((1, 1, 9), (1, 2, 3)), 9, [1, 1])

    def test_zero_weights(self):
        r = solve(E((1, 2, 0), (2, 3, 0)))
        self.assertGreaterEqual(len(r.route), 2)
        self.assertEqual(route_length(E((1, 2, 0), (2, 3, 0)), r.route), 0)

    def test_disconnected_components(self):
        self.check(E((1, 2, 1), (3, 4, 10), (4, 5, 10)), 20, [3, 4, 5])


def random_graph(rng, n, m, *, allow_loops=True, allow_parallel=True, chainy=False):
    edges = []
    if chainy:
        # 鉄道網っぽく: 少数の分岐駅を、途中駅を挟んだ区間で結ぶ
        hubs = list(range(1, n + 1))
        nxt = n + 1
        for _ in range(m):
            a, b = rng.sample(hubs, 2)
            prev = a
            for _ in range(rng.randint(0, 3)):
                edges.append(Edge(prev, nxt, round(rng.uniform(0, 10), 2)))
                prev, nxt = nxt, nxt + 1
            edges.append(Edge(prev, b, round(rng.uniform(0, 10), 2)))
        for _ in range(rng.randint(0, 3)):  # 終着駅への支線
            prev = rng.choice(hubs)
            for _ in range(rng.randint(1, 3)):
                edges.append(Edge(prev, nxt, round(rng.uniform(0, 10), 2)))
                prev, nxt = nxt, nxt + 1
        return edges
    seen = set()
    max_pairs = n * (n - 1) // 2 + (n if allow_loops else 0)
    if not allow_parallel:
        m = min(m, max_pairs)
    while len(edges) < m:
        u, v = rng.randint(1, n), rng.randint(1, n)
        if u == v and (not allow_loops or rng.random() < 0.8):
            continue
        key = frozenset((u, v))
        if key in seen and not allow_parallel:
            continue
        seen.add(key)
        edges.append(Edge(u, v, round(rng.uniform(0, 10), 2)))
    return edges


class SolverAgainstBruteForce(unittest.TestCase):
    def compare(self, edges):
        expected = brute_force(edges)
        # ヒューリスティックが最適解を見つけると厳密探索の誤りが隠れるので、両方の設定で確かめる
        for use_heuristic in (True, False):
            r = solve(edges, use_heuristic=use_heuristic)
            msg = f"use_heuristic={use_heuristic} edges={edges}"
            self.assertTrue(r.optimal)
            self.assertAlmostEqual(r.length, expected, places=6, msg=msg)
            self.assertAlmostEqual(route_length(edges, r.route), expected, places=6, msg=msg)

    def test_random_general(self):
        rng = random.Random(20280401)
        for _ in range(400):
            n = rng.randint(1, 8)
            m = rng.randint(1, 14)
            self.compare(random_graph(rng, n, m))

    def test_random_sparse(self):
        rng = random.Random(7)
        for _ in range(300):
            n = rng.randint(2, 12)
            m = rng.randint(1, n + 2)
            self.compare(random_graph(rng, n, m, allow_loops=False, allow_parallel=False))

    def test_random_railway_like(self):
        rng = random.Random(42)
        for _ in range(300):
            n = rng.randint(2, 6)
            m = rng.randint(1, 8)
            self.compare(random_graph(rng, n, m, chainy=True))


def complete_graph(rng, n):
    return [
        Edge(u, v, round(rng.uniform(1, 100), 2))
        for u in range(1, n + 1)
        for v in range(u + 1, n + 1)
    ]


class TimeLimit(unittest.TestCase):
    def assertValidRoute(self, edges, r):
        self.assertGreaterEqual(len(r.route), 2)
        self.assertAlmostEqual(route_length(edges, r.route), r.length, places=6)

    def test_returns_valid_route_when_time_runs_out(self):
        rng = random.Random(3)
        edges = random_graph(rng, 60, 150, allow_loops=False, allow_parallel=False)
        r = solve(edges, time_limit=0.3)
        # 60 駅・150 辺のランダムグラフは 0.3 秒では到底解き切れない（数分以上かかる）規模にしてある
        self.assertFalse(r.optimal)
        self.assertGreater(len(r.route), 2)
        self.assertValidRoute(edges, r)

    def test_tiny_time_limit_does_not_crash(self):
        # ヒューリスティックが 1 歩も進めないうちに時間切れになっても、経路を返す
        edges = E((1, 2, 8.54), (2, 3, 3.11), (3, 1, 2.19), (3, 4, 4), (4, 1, 1.4))
        for limit in (1e-9, 1e-6, 1e-4):
            r = solve(edges, time_limit=limit)
            self.assertValidRoute(edges, r)

    def test_heuristic_respects_time_limit_on_dense_graph(self):
        # 次数が大きいとヒューリスティックの浅い探索 1 回が重い。それでも時間制限を大きく超えない
        edges = complete_graph(random.Random(1), 40)
        started = time.monotonic()
        r = solve(edges, time_limit=0.5)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 3.0)
        self.assertFalse(r.optimal)
        self.assertValidRoute(edges, r)


class Interrupt(unittest.TestCase):
    def test_ctrl_c_during_heuristic_still_returns_route(self):
        edges = E((1, 2, 8.54), (2, 3, 3.11), (3, 1, 2.19), (3, 4, 4), (4, 1, 1.4), (4, 5, 2))
        with mock.patch("longest_path.solver.heuristic_path", side_effect=KeyboardInterrupt):
            r = solve(edges)
        self.assertTrue(r.interrupted)
        self.assertFalse(r.optimal)
        self.assertGreaterEqual(len(r.route), 2)
        self.assertAlmostEqual(route_length(edges, r.route), r.length, places=6)

    def test_ctrl_c_during_preprocessing_returns_empty(self):
        with mock.patch("longest_path.solver.build_network", side_effect=KeyboardInterrupt):
            r = solve(E((1, 2, 1)))
        self.assertTrue(r.interrupted)
        self.assertEqual(r.route, [])


if __name__ == "__main__":
    unittest.main()
