import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from longest_path import cli


class _Stdout:
    def __init__(self):
        self.buffer = io.BytesIO()


class CliTest(unittest.TestCase):
    def run_cli(self, argv, stdin_bytes):
        stdin = mock.Mock()
        stdin.buffer = io.BytesIO(stdin_bytes)
        stdout, stderr = _Stdout(), io.StringIO()
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
            with redirect_stderr(stderr):
                code = cli.main(argv)
        return code, stdout.buffer.getvalue(), stderr.getvalue()

    def test_sample(self):
        code, out, err = self.run_cli([], b"1, 2, 8.54\r\n2, 3, 3.11\r\n3, 1, 2.19\r\n3, 4, 4\r\n4, 1, 1.4\r\n")
        self.assertEqual(code, 0)
        self.assertEqual(out, b"1\r\n2\r\n3\r\n4\r\n1\r\n")
        self.assertEqual(err, "")

    def test_rejects_invalid_time_limit(self):
        for bad in ("-1", "nan", "abc"):
            with self.subTest(bad=bad), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    cli.main(["-t", bad])
                self.assertEqual(cm.exception.code, 2)

    def test_interrupted_before_any_route(self):
        with mock.patch("longest_path.solver.build_network", side_effect=KeyboardInterrupt):
            code, out, err = self.run_cli([], b"1, 2, 1\r\n")
        self.assertEqual(code, 130)
        self.assertEqual(out, b"")
        self.assertIn("before any route was found", err)


if __name__ == "__main__":
    unittest.main()
