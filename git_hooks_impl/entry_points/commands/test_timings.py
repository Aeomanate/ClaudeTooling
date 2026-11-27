#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""`mr script test_timings` - lists the slowest tests in the suite.

Runs the full git_hooks_impl/tests suite once and times each test
individually, using a custom unittest.TextTestResult subclass. Report only
- it does not replace `mr verify` and does not gate anything on its own.
"""
import sys
import time
import unittest

HELP = """\
mr script test_timings
mr script test_timings <N>

Runs the test suite once and prints the N slowest tests, in order.

Examples:
  mr script test_timings      # top 20 (the default)
  mr script test_timings 5    # top 5 only

This is a report only. It does not gate anything and does not replace
`mr verify` - see `mr script leak_check` for the wall-time leak flag that
uses the suite's total time, not individual test times.

Exit code: always 0, unless the suite itself fails to run.
"""

_DEFAULT_TOP_N = 20


class _TimedResult(unittest.TextTestResult):
    def startTest(self, test):  # noqa: N802 - overriding unittest's own camelCase API
        self._start = time.time()
        super().startTest(test)

    def stopTest(self, test):  # noqa: N802 - overriding unittest's own camelCase API
        elapsed = time.time() - self._start
        self.timings.append((elapsed, str(test)))
        super().stopTest(test)


class _TimedRunner(unittest.TextTestRunner):
    def _makeResult(self):  # noqa: N802 - overriding unittest's own camelCase API
        result = _TimedResult(self.stream, self.descriptions, self.verbosity)
        result.timings = []
        return result


def collect_timings(start_dir='git_hooks_impl/tests'):
    """Runs the suite once, returns [(elapsed_seconds, test_id), ...]."""
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir)
    runner = _TimedRunner(verbosity=0, stream=sys.stderr)
    result = runner.run(suite)
    return result.timings


def run(argv: list) -> int:
    if argv and argv[0] in ('--help', '-h'):
        print(HELP)
        return 0

    top_n = _DEFAULT_TOP_N
    if argv:
        try:
            top_n = int(argv[0])
        except ValueError:
            print(f"Usage: mr script test_timings [N] - '{argv[0]}' is not a number")
            return 1

    timings = collect_timings()
    slowest = sorted(timings, reverse=True)[:top_n]

    print(f'=== Top {len(slowest)} slowest tests ===')
    for elapsed, test_id in slowest:
        print(f'{elapsed:.3f}s  {test_id}')
    print()
    print(f'Total measured: {sum(t for t, _ in timings):.3f}s across {len(timings)} tests')
    return 0


if __name__ == '__main__':
    sys.exit(run(sys.argv[1:]))
