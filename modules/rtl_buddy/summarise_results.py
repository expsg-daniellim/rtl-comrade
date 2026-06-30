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


import re
import sys

VERDICT_COLOURS = {"PASS": "\033[1;92m", "FAIL": "\033[1;91m", "NA": "\033[1;93m"}  # SKIP left plain — rtl_buddy parity
COLOUR_END = "\033[0m"


def colourise(text:str) -> str:  # mirror PassFailFormatter (rtl_buddy.py:52-60): wrap verdict tokens, SKIP uncoloured
    for tok, colour in VERDICT_COLOURS.items():
        text = re.sub(rf"\b{tok}\b", f"{colour}{tok}{COLOUR_END}", text)
    return text


class PrintSummaryMod:
    def run(self, table):
        print(colourise(table) if sys.stdout.isatty() else table)
