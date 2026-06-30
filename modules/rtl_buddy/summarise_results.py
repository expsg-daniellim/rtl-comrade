from __future__ import annotations
import structlog

log = structlog.get_logger()


class SummariseResultsMod:
    def __init__(self):
        self.rows = []  # one TestResult per invocation; run-long, fresh per run

    def run(self, result):  # the any contract delivers one TestResult under `result`
        self.rows.append(result)

    def finalise(self):  # per-run teardown hook, at run end
        if len(self.rows) == 0:  # list-mode / CRITICAL abort → emit nothing
            return None
        lines = ["\nTest Results Summary"]
        for r in self.rows:  # rtl_buddy.py:203-205 widths; None → 'NA' (test_results.py:23-27)
            lines.append(f"{r.test_name or 'NA':<30} {r.result or 'NA':<8} {r.desc or 'NA':<30}")
        table = "\n".join(lines)
        n_fail = sum(1 for r in self.rows if r.result == "FAIL")
        if n_fail > 0:  # consolidated summary signal → drives the exit (handler.failure)
            log.error("test_failures", count=n_fail)
        return ("table", table)  # emit the plain table on the `table` port
