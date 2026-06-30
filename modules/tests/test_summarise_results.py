"""Tests for modules/rtl_buddy/summarise_results.py — SummariseResultsMod (spec 10d)."""

import importlib.util
import structlog.testing
from pathlib import Path

from modules.rtl_buddy.schema import TestResult

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_summarise_results",
    Path(__file__).parent.parent / "rtl_buddy" / "summarise_results.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SummariseResultsMod = _mod.SummariseResultsMod


def _pass_result(test_name="test_a", desc="all good"):
    return TestResult.parse(key="k", test_name=test_name, result="PASS", desc=desc)


def _fail_result(test_name="test_b", desc="assertion error"):
    return TestResult.compile_fail(key="k", test_name=test_name)


def _skip_result(test_name="test_c", desc="below reglvl"):
    return TestResult.skip(key="k", test_name=test_name, desc=desc)


def _na_result(test_name="test_d", desc="Stopped early at pre"):
    return TestResult.early_stop(key="k", test_name=test_name, desc=desc)


# ---------------------------------------------------------------------------
# No results → finalise() is a no-op
# ---------------------------------------------------------------------------


def test_no_rows_finalise_returns_none():
    mod = SummariseResultsMod()
    result = mod.finalise()
    assert result is None


def test_no_rows_no_table_emission(logging_handler):
    mod = SummariseResultsMod()
    result = mod.finalise()
    assert result is None
    assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# Table render — header and rows in arrival order
# table.splitlines() → ['', 'Test Results Summary', row0, row1, …]
# ---------------------------------------------------------------------------


def test_single_pass_result_table():
    r = _pass_result(test_name="my_test", desc="passed fine")
    mod = SummariseResultsMod()
    mod.run(result=r)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    assert port == "table"
    assert "\nTest Results Summary" in table
    assert "my_test" in table
    assert "PASS" in table
    assert "passed fine" in table


def test_table_rows_in_arrival_order():
    r1 = _pass_result(test_name="alpha", desc="first")
    r2 = _fail_result(test_name="beta")
    r3 = _skip_result(test_name="gamma", desc="skipped")
    mod = SummariseResultsMod()
    mod.run(result=r1)
    mod.run(result=r2)
    mod.run(result=r3)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    assert port == "table"
    lines = table.splitlines()
    # ['', 'Test Results Summary', row0, row1, row2]
    assert len(lines) == 5
    assert lines[1] == "Test Results Summary"
    assert lines[2].startswith("alpha")
    assert lines[3].startswith("beta")
    assert lines[4].startswith("gamma")


def test_table_first_column_is_test_name():
    r = _pass_result(test_name="specific_test", desc="desc here")
    mod = SummariseResultsMod()
    mod.run(result=r)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    lines = table.splitlines()
    row = lines[2]  # data starts at index 2
    assert row.startswith("specific_test")


def test_column_widths_match_rtl_buddy():
    r = _pass_result(test_name="t", desc="d")
    mod = SummariseResultsMod()
    mod.run(result=r)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    lines = table.splitlines()
    row = lines[2]
    expected = f"{'t':<30} {'PASS':<8} {'d':<30}"
    assert row == expected


# ---------------------------------------------------------------------------
# Falsy field → 'NA'
# ---------------------------------------------------------------------------


def test_empty_desc_renders_as_na():
    r = TestResult.parse(key="k", test_name="test_x", result="PASS", desc="")
    mod = SummariseResultsMod()
    mod.run(result=r)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    lines = table.splitlines()
    row = lines[2]
    assert "NA" in row


def test_empty_test_name_renders_as_na():
    r = TestResult.parse(key="k", test_name="", result="PASS", desc="some desc")
    mod = SummariseResultsMod()
    mod.run(result=r)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    lines = table.splitlines()
    row = lines[2]
    assert row.startswith("NA")


# ---------------------------------------------------------------------------
# Plain text — no ANSI escape codes
# ---------------------------------------------------------------------------


def test_table_is_plain_no_ansi():
    r1 = _pass_result()
    r2 = _fail_result()
    mod = SummariseResultsMod()
    mod.run(result=r1)
    mod.run(result=r2)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    assert "\x1b" not in table


# ---------------------------------------------------------------------------
# State accumulates across run() calls
# ---------------------------------------------------------------------------


def test_k_run_calls_produce_k_rows():
    results = [_pass_result(test_name=f"t{i}", desc=f"d{i}") for i in range(5)]
    mod = SummariseResultsMod()
    for r in results:
        mod.run(result=r)
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    lines = table.splitlines()
    assert len(lines) == 7  # '' + header + 5 rows


def test_single_run_call_produces_one_row():
    mod = SummariseResultsMod()
    mod.run(result=_pass_result(test_name="only_one"))
    with structlog.testing.capture_logs():
        port, table = mod.finalise()
    lines = table.splitlines()
    assert len(lines) == 3  # '' + header + 1 row
    assert "only_one" in lines[2]


# ---------------------------------------------------------------------------
# Consolidated FAIL signal
# ---------------------------------------------------------------------------


def test_one_fail_emits_log_error(logging_handler):
    mod = SummariseResultsMod()
    mod.run(result=_fail_result(test_name="bad"))
    port, table = mod.finalise()
    assert port == "table"
    assert logging_handler.failure is True


def test_fail_count_in_log_matches_fail_rows(logging_handler):
    mod = SummariseResultsMod()
    mod.run(result=_fail_result(test_name="f1"))
    mod.run(result=_fail_result(test_name="f2"))
    mod.run(result=_pass_result(test_name="p1"))
    port, table = mod.finalise()
    assert port == "table"
    assert logging_handler.failure is True


def test_fail_table_still_emitted(logging_handler):
    mod = SummariseResultsMod()
    mod.run(result=_fail_result(test_name="f1"))
    port, table = mod.finalise()
    assert port == "table"
    assert table is not None
    assert "\nTest Results Summary" in table


def test_multiple_fails_one_log_error(logging_handler):
    mod = SummariseResultsMod()
    for i in range(3):
        mod.run(result=_fail_result(test_name=f"f{i}"))
    port, table = mod.finalise()
    assert port == "table"
    assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# No false exit — PASS/SKIP/NA rows do not trigger log.error
# ---------------------------------------------------------------------------


def test_all_pass_no_log_error(logging_handler):
    mod = SummariseResultsMod()
    mod.run(result=_pass_result(test_name="p1"))
    mod.run(result=_pass_result(test_name="p2"))
    port, table = mod.finalise()
    assert port == "table"
    assert logging_handler.failure is False


def test_all_skip_no_log_error(logging_handler):
    mod = SummariseResultsMod()
    mod.run(result=_skip_result(test_name="s1"))
    mod.run(result=_skip_result(test_name="s2"))
    port, table = mod.finalise()
    assert port == "table"
    assert logging_handler.failure is False


def test_early_stop_na_no_log_error(logging_handler):
    # An early-stop NA (exit-0 divergence) must not drive the consolidated exit
    mod = SummariseResultsMod()
    mod.run(result=_na_result(test_name="stopped"))
    port, table = mod.finalise()
    assert port == "table"
    assert logging_handler.failure is False


def test_pass_skip_and_early_stop_na_no_log_error(logging_handler):
    mod = SummariseResultsMod()
    mod.run(result=_pass_result(test_name="p1"))
    mod.run(result=_skip_result(test_name="s1"))
    mod.run(result=_na_result(test_name="na1"))
    port, table = mod.finalise()
    assert port == "table"
    assert logging_handler.failure is False


def test_pass_skip_and_na_table_still_emitted(logging_handler):
    mod = SummariseResultsMod()
    mod.run(result=_pass_result(test_name="p1"))
    mod.run(result=_skip_result(test_name="s1"))
    mod.run(result=_na_result(test_name="na1"))
    port, table = mod.finalise()
    assert "\nTest Results Summary" in table
    lines = table.splitlines()
    assert len(lines) == 5  # '' + header + 3 rows
