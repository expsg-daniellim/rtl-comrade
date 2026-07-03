"""Tests for graphs/log/summary.py — SummaryProcessor (spec 10c)."""

import importlib.util
import inspect
import sys
import typing
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

import pytest
from structlog.exceptions import DropEvent

_spec = importlib.util.spec_from_file_location(
	"graphs_log_summary",
	Path(__file__).parent.parent / "log" / "summary.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["graphs_log_summary"] = _mod  # must be in sys.modules before exec so @serde/@dataclass can resolve cls.__module__
_spec.loader.exec_module(_mod)
SummaryProcessor = _mod.SummaryProcessor
VERDICT_COLOURS = _mod.VERDICT_COLOURS
COLOUR_END = _mod.COLOUR_END


def _make(config=None):
	return SummaryProcessor(config or SummaryProcessor.Config())


def _event(name, test_name="t1", result="PASS", desc="a test", key="k1"):
	return {"event": name, "test_name": test_name, "result": result, "desc": desc, "key": key}


# ---------------------------------------------------------------------------
# Table render — N test_result events produce one row each, in arrival order
# ---------------------------------------------------------------------------


def test_table_render_arrival_order(capsys):
	proc = _make()
	events = [
		_event("test_result", test_name="t1", result="PASS", desc="first"),
		_event("test_result", test_name="t2", result="SKIP", desc="second"),
		_event("test_result", test_name="t3", result="FAIL", desc="third"),
		_event("test_result", test_name="t4", result="NA", desc="fourth"),
	]
	for ev in events:
		with pytest.raises(DropEvent):
			proc(None, "info", ev)
	proc.finalise()
	out = capsys.readouterr().out
	assert "Test Results Summary" in out
	lines = [l for l in out.splitlines() if l.strip()]
	assert len(lines) == 5  # header + 4 rows
	assert "t1" in lines[1]
	assert "t2" in lines[2]
	assert "t3" in lines[3]
	assert "t4" in lines[4]


# ---------------------------------------------------------------------------
# Colourisation gating — TTY: PASS/FAIL/NA wrapped, SKIP plain; non-TTY: no ANSI
# ---------------------------------------------------------------------------


def test_colourisation_tty(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: True)
	proc = _make()
	for name, result in [("pass_test", "PASS"), ("fail_test", "FAIL"), ("na_test", "NA"), ("skip_test", "SKIP")]:
		with pytest.raises(DropEvent):
			proc(None, "info", _event("test_result", test_name=name, result=result, desc="d"))
	proc.finalise()
	out = capsys.readouterr().out
	assert VERDICT_COLOURS["PASS"] in out
	assert VERDICT_COLOURS["FAIL"] in out
	assert VERDICT_COLOURS["NA"] in out
	assert COLOUR_END in out
	# SKIP stays plain — no colour code wrapping SKIP
	skip_line = next(l for l in out.splitlines() if "skip_test" in l)
	assert "\033[" not in skip_line


def test_no_colourisation_non_tty(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: False)
	proc = _make()
	for name, result in [("fail_test", "FAIL"), ("pass_test", "PASS"), ("na_test", "NA")]:
		with pytest.raises(DropEvent):
			proc(None, "info", _event("test_result", test_name=name, result=result, desc="d"))
	proc.finalise()
	out = capsys.readouterr().out
	assert "\033[" not in out


# ---------------------------------------------------------------------------
# Missing field → renders as 'NA'
# ---------------------------------------------------------------------------


def test_missing_field_renders_na(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: False)
	proc = _make()
	ev = {"event": "test_result"}  # no test_name, result, desc
	with pytest.raises(DropEvent):
		proc(None, "info", ev)
	proc.finalise()
	out = capsys.readouterr().out
	lines = [l for l in out.splitlines() if l.strip()]
	row = lines[1]
	assert row.startswith("NA")
	assert "NA" in row


# ---------------------------------------------------------------------------
# Watched failure event (not in suppress) → row appended, event returned unchanged
# ---------------------------------------------------------------------------


def test_watched_failure_not_suppressed():
	config = SummaryProcessor.Config(events=["test_result", "compile_failed"], suppress=["test_result"])
	proc = SummaryProcessor(config)
	ev = _event("compile_failed", test_name="t_fail", result="FAIL", desc="compile error")
	returned = proc(None, "error", ev)
	assert returned is ev
	assert len(proc.rows) == 1
	assert proc.rows[0]["test_name"] == "t_fail"


# ---------------------------------------------------------------------------
# No events → finalise() is a no-op
# ---------------------------------------------------------------------------


def test_finalise_noop_no_events(capsys):
	proc = _make()
	proc.finalise()
	out = capsys.readouterr().out
	assert out == ""


# ---------------------------------------------------------------------------
# test_result event → DropEvent raised, row accumulated
# ---------------------------------------------------------------------------


def test_test_result_drop_event_and_row():
	proc = _make()
	ev = _event("test_result")
	with pytest.raises(DropEvent):
		proc(None, "info", ev)
	assert len(proc.rows) == 1
	assert proc.rows[0]["test_name"] == "t1"


# ---------------------------------------------------------------------------
# Non-watched event → event_dict returned unchanged, no DropEvent
# ---------------------------------------------------------------------------


def test_non_watched_passthrough():
	proc = _make()
	ev = {"event": "git_state", "dirty": False}
	returned = proc(None, "info", ev)
	assert returned is ev
	assert proc.rows == []


def test_arbitrary_module_log_passthrough():
	proc = _make()
	ev = {"event": "some_module_log", "data": 42}
	returned = proc(None, "debug", ev)
	assert returned is ev
	assert proc.rows == []


# ---------------------------------------------------------------------------
# Config-driven watch-list — collects only_this, ignores test_result, drops nothing
# ---------------------------------------------------------------------------


def test_config_driven_watchlist(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: False)
	config = SummaryProcessor.Config(events=["only_this"], suppress=[])
	proc = SummaryProcessor(config)
	watched = _event("only_this", test_name="t_watched", result="PASS", desc="watched")
	not_watched = _event("test_result", test_name="t_ignored", result="FAIL", desc="ignored")
	returned_w = proc(None, "info", watched)
	returned_n = proc(None, "info", not_watched)
	assert returned_w is watched  # not suppressed (suppress=[])
	assert returned_n is not_watched  # not watched
	assert len(proc.rows) == 1
	assert proc.rows[0]["test_name"] == "t_watched"
	proc.finalise()
	out = capsys.readouterr().out
	assert "t_watched" in out
	assert "t_ignored" not in out


# ---------------------------------------------------------------------------
# State persists across calls — K calls → K rows at finalise
# ---------------------------------------------------------------------------


def test_state_persists_across_calls(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: False)
	proc = _make()
	K = 5
	for i in range(K):
		with pytest.raises(DropEvent):
			proc(None, "info", _event("test_result", test_name=f"t{i}", result="PASS", desc="d"))
	assert len(proc.rows) == K
	proc.finalise()
	out = capsys.readouterr().out
	lines = [l for l in out.splitlines() if l.strip()]
	assert len(lines) == K + 1  # header + K rows


# ---------------------------------------------------------------------------
# __call__ signature satisfies strict processor contract
# ---------------------------------------------------------------------------


def test_call_signature_contract():
	proc = _make()
	sig = inspect.signature(proc.__call__)
	params = list(sig.parameters.values())
	assert len(params) == 3
	p_logger, p_method_name, p_event_dict = params
	assert p_logger.name == "logger"
	# from __future__ import annotations defers annotation evaluation; resolve via get_type_hints
	hints = typing.get_type_hints(proc.__call__)
	assert hints["method_name"] is str
	assert "event_dict" in hints
	assert "return" in hints
