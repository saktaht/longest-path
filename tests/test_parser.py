import unittest

from longest_path import Edge, parse_edges


class ParserTest(unittest.TestCase):
    def test_sample_with_crlf(self):
        text = "1, 2, 8.54\r\n2, 3, 3.11\r\n3, 1, 2.19\r\n3, 4, 4\r\n4, 1, 1.4\r\n"
        edges, warnings = parse_edges(text)
        self.assertEqual(warnings, [])
        self.assertEqual(edges[0], Edge(1, 2, 8.54))
        self.assertEqual(edges[3], Edge(3, 4, 4.0))
        self.assertEqual(len(edges), 5)

    def test_whitespace_and_lf(self):
        edges, warnings = parse_edges("   1 ,2,   3.5   \n\n 10,  20 ,1e2\n")
        self.assertEqual(warnings, [])
        self.assertEqual(edges, [Edge(1, 2, 3.5), Edge(10, 20, 100.0)])

    def test_invalid_lines_are_skipped(self):
        text = "\n".join([
            "1, 2",            # 列が足りない
            "a, 2, 3",         # 数値でない
            "0, 2, 3",         # ID が正でない
            "1, 2, -1",        # 負の距離
            "1, 2, nan",       # 非数
            "1.5, 2, 3",       # ID が整数でない
            "3, 4, 5",         # 正常
        ])
        edges, warnings = parse_edges(text)
        self.assertEqual(edges, [Edge(3, 4, 5.0)])
        self.assertEqual(len(warnings), 6)

    def test_non_ascii_digits_are_rejected(self):
        edges, warnings = parse_edges("\u0661, 2, 3\n1, \uff12, 3\n")  # アラビア数字の 1、全角の 2
        self.assertEqual(edges, [])
        self.assertEqual(len(warnings), 2)


if __name__ == "__main__":
    unittest.main()
