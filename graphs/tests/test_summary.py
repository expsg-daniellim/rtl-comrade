"""Tests for graphs/log/summary.py — ConsoleSummaryProcessor, FileSummaryProcessor, SummaryAccumulator."""

import importlib.util
import inspect
import sys
import typing
from pathlib import Path
from unittest.mock import patch

import pytest
from structlog.exceptions import DropEvent

_spec = importlib.util.spec_from_file_location(
	"graphs_log_summary",
	Path(__file__).parent.parent / "log" / "summary.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["graphs_log_summary"] = _mod
_spec.loader.exec_module(_mod)
SummaryAccumulator = _mod.SummaryAccumulator
ConsoleSummaryProcessor = _mod.ConsoleSummaryProcessor
FileSummaryProcessor = _mod.FileSummaryProcessor
VERDICT_COLOURS = _mod.VERDICT_COLOURS
COLOUR_END = _mod.COLOUR_END
DESC_BUILDERS = _mod.DESC_BUILDERS
FAIL_EVENTS = _mod.FAIL_EVENTS
build_events = _mod.build_events


def _make_accumulator(events=None, suppress=None):
	return SummaryAccumulator(events or {"compile_failed": "FAIL", "parse_log_passed": "PASS", "test_skipped": "SKIP", "test_stopped_early": "NA"}, suppress or set())


def _make_console(config=None):
	return ConsoleSummaryProcessor(config or ConsoleSummaryProcessor.Config())


def _make_file(out, config=None):
	return FileSummaryProcessor(config or FileSummaryProcessor.Config(out=out))


# ===========================================================================
# SummaryAccumulator — __call__ accumulation
# ===========================================================================


def test_accumulator_watched_suppressed_event():
	acc = SummaryAccumulator(events={"compile_failed": "FAIL"}, suppress={"compile_failed"})
	ev = {"event": "compile_failed", "test_name": "t1", "key": "k1"}
	with pytest.raises(DropEvent):
		acc(None, "error", ev)
	assert len(acc.rows) == 1
	assert acc.rows[0]["test_name"] == "t1"


def test_accumulator_non_watched_passthrough():
	acc = _make_accumulator()
	ev = {"event": "git_state", "dirty": False}
	returned = acc(None, "info", ev)
	assert returned is ev
	assert len(acc.rows) == 0


def test_accumulator_watched_not_suppressed():
	acc = SummaryAccumulator(events={"compile_failed": "FAIL", "parse_log_passed": "PASS"}, suppress={"parse_log_passed"})
	ev = {"event": "compile_failed", "test_name": "t_fail", "key": "k1"}
	returned = acc(None, "error", ev)
	assert returned is ev
	assert len(acc.rows) == 1
	assert acc.rows[0]["result"] == "FAIL"


def test_accumulator_state_persists():
	acc = SummaryAccumulator(events={"compile_failed": "FAIL"}, suppress={"compile_failed"})
	for i in range(5):
		with pytest.raises(DropEvent):
			acc(None, "error", {"event": "compile_failed", "test_name": f"t{i}", "key": f"k{i}"})
	assert len(acc.rows) == 5


def test_accumulator_categorises_events():
	acc = _make_accumulator()
	acc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	acc(None, "info", {"event": "parse_log_passed", "test_name": "t2", "key": "k2", "desc": "ok"})
	acc(None, "info", {"event": "test_skipped", "test_name": "t3", "key": "k3", "reason": "filtered"})
	acc(None, "info", {"event": "test_stopped_early", "test_name": "t4", "key": "k4", "phase": "pre"})
	assert acc.rows[0]["result"] == "FAIL"
	assert acc.rows[1]["result"] == "PASS"
	assert acc.rows[2]["result"] == "SKIP"
	assert acc.rows[3]["result"] == "NA"


# ===========================================================================
# SummaryAccumulator — render_table
# ===========================================================================


def test_render_table_arrival_order():
	acc = _make_accumulator()
	acc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	acc(None, "info", {"event": "parse_log_passed", "test_name": "t2", "key": "k2", "desc": "ok"})
	acc(None, "info", {"event": "test_skipped", "test_name": "t3", "key": "k3", "reason": "r"})
	acc(None, "info", {"event": "test_stopped_early", "test_name": "t4", "key": "k4", "phase": "pre"})
	table = acc.render_table()
	assert table is not None
	assert "Test Results Summary" in table
	lines = [l for l in table.splitlines() if l.strip()]
	assert len(lines) == 6  # header + 4 rows + failure count
	assert "t1" in lines[1]
	assert "t2" in lines[2]
	assert "t3" in lines[3]
	assert "t4" in lines[4]


def test_render_table_none_when_empty():
	acc = _make_accumulator()
	assert acc.render_table() is None


def test_render_table_failure_count():
	acc = SummaryAccumulator(events={"compile_failed": "FAIL", "sim_timeout": "FAIL", "parse_log_passed": "PASS"}, suppress=set())
	acc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	acc(None, "error", {"event": "sim_timeout", "test_name": "t2", "key": "k2"})
	acc(None, "info", {"event": "parse_log_passed", "test_name": "t3", "key": "k3", "desc": "ok"})
	table = acc.render_table()
	assert "2 failures" in table


def test_render_table_single_failure_no_plural():
	acc = SummaryAccumulator(events={"compile_failed": "FAIL", "parse_log_passed": "PASS"}, suppress=set())
	acc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	acc(None, "info", {"event": "parse_log_passed", "test_name": "t2", "key": "k2", "desc": "ok"})
	table = acc.render_table()
	assert "1 failure" in table
	assert "1 failures" not in table


def test_render_table_no_failure_count_when_all_pass():
	acc = SummaryAccumulator(events={"parse_log_passed": "PASS"}, suppress=set())
	acc(None, "info", {"event": "parse_log_passed", "test_name": "t1", "key": "k1", "desc": "ok"})
	table = acc.render_table()
	assert "failure" not in table


def test_render_table_missing_fields_as_na():
	acc = SummaryAccumulator(events={"compile_failed": "FAIL"}, suppress=set())
	acc(None, "error", {"event": "compile_failed"})
	table = acc.render_table()
	assert table is not None
	lines = [l for l in table.splitlines() if l.strip()]
	row = lines[1]
	assert row.startswith("NA")


# ===========================================================================
# DESC_BUILDERS
# ===========================================================================


def test_desc_builders_compile_failed():
	assert DESC_BUILDERS["compile_failed"]({}) == "Compile failed"


def test_desc_builders_sim_timeout():
	assert DESC_BUILDERS["sim_timeout"]({}) == "Sim hit timeout"


def test_desc_builders_preproc_script_not_found():
	assert DESC_BUILDERS["preproc_script_not_found"]({"preproc_path": "/x/y.py"}) == "preproc script not found: /x/y.py"


def test_desc_builders_model_not_found():
	assert DESC_BUILDERS["model_not_found"]({"model": "m", "model_path": "/p"}) == "model 'm' not in /p"


def test_desc_builders_parse_log_passed():
	assert DESC_BUILDERS["parse_log_passed"]({"desc": "all ok"}) == "all ok"


def test_desc_builders_test_skipped():
	assert DESC_BUILDERS["test_skipped"]({"reason": "lvl too high"}) == "lvl too high"


def test_desc_builders_test_stopped_early():
	assert DESC_BUILDERS["test_stopped_early"]({"phase": "comp"}) == "Stopped early at comp"


def test_desc_builders_coverage():
	events_with_builders = set(FAIL_EVENTS) | {"parse_log_passed", "parse_uvm_passed", "parse_log_unknown", "test_skipped", "test_stopped_early"}
	assert events_with_builders == set(DESC_BUILDERS.keys())


# ===========================================================================
# build_events
# ===========================================================================


def test_build_events_from_config():
	config = ConsoleSummaryProcessor.Config()
	events = build_events(config)
	for name in FAIL_EVENTS:
		assert events[name] == "FAIL"
	assert events["parse_log_passed"] == "PASS"
	assert events["parse_uvm_passed"] == "PASS"
	assert events["test_skipped"] == "SKIP"
	assert events["test_stopped_early"] == "NA"
	assert events["parse_log_unknown"] == "NA"


# ===========================================================================
# SummaryAccumulator — __call__ signature contract
# ===========================================================================


def test_call_signature_contract():
	acc = _make_accumulator()
	sig = inspect.signature(acc.__call__)
	params = list(sig.parameters.values())
	assert len(params) == 3
	hints = typing.get_type_hints(acc.__call__)
	assert hints["method_name"] is str
	assert "event_dict" in hints
	assert "return" in hints


# ===========================================================================
# ConsoleSummaryProcessor — finalise
# ===========================================================================


def test_console_finalise_prints_table(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: False)
	proc = _make_console()
	proc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	proc(None, "info", {"event": "parse_log_passed", "test_name": "t2", "key": "k2", "desc": "ok"})
	proc.finalise()
	out = capsys.readouterr().out
	assert "Test Results Summary" in out
	assert "t1" in out
	assert "t2" in out


def test_console_colourisation_tty(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: True)
	proc = _make_console()
	proc(None, "info", {"event": "parse_log_passed", "test_name": "pass_test", "key": "k1", "desc": "ok"})
	proc(None, "error", {"event": "compile_failed", "test_name": "fail_test", "key": "k2"})
	proc(None, "info", {"event": "test_stopped_early", "test_name": "na_test", "key": "k3", "phase": "pre"})
	proc(None, "info", {"event": "test_skipped", "test_name": "skip_test", "key": "k4", "reason": "r"})
	proc.finalise()
	out = capsys.readouterr().out
	assert VERDICT_COLOURS["PASS"] in out
	assert VERDICT_COLOURS["FAIL"] in out
	assert VERDICT_COLOURS["NA"] in out
	assert COLOUR_END in out
	skip_line = next(l for l in out.splitlines() if "skip_test" in l)
	assert "\033[" not in skip_line


def test_console_no_colourisation_non_tty(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: False)
	proc = _make_console()
	proc(None, "error", {"event": "compile_failed", "test_name": "fail_test", "key": "k1"})
	proc(None, "info", {"event": "parse_log_passed", "test_name": "pass_test", "key": "k2", "desc": "ok"})
	proc.finalise()
	out = capsys.readouterr().out
	assert "\033[" not in out


def test_console_finalise_noop_empty(capsys):
	proc = _make_console()
	proc.finalise()
	out = capsys.readouterr().out
	assert out == ""


def test_console_config_defaults():
	config = ConsoleSummaryProcessor.Config()
	assert config.fail == list(FAIL_EVENTS)
	assert config.pass_ == ["parse_log_passed", "parse_uvm_passed"]
	assert config.skip == ["test_skipped"]
	assert config.na == ["test_stopped_early", "parse_log_unknown"]
	assert config.suppress == []


# ===========================================================================
# FileSummaryProcessor — finalise
# ===========================================================================


def test_file_finalise_writes_table(tmp_path):
	out = tmp_path / "run.log"
	proc = _make_file(out)
	proc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	proc(None, "info", {"event": "parse_log_passed", "test_name": "t2", "key": "k2", "desc": "ok"})
	proc.finalise()
	content = out.read_text(encoding="utf-8")
	assert "Test Results Summary" in content
	assert "t1" in content
	assert "t2" in content


def test_file_finalise_no_ansi(tmp_path):
	out = tmp_path / "run.log"
	proc = _make_file(out)
	proc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	proc(None, "info", {"event": "parse_log_passed", "test_name": "t2", "key": "k2", "desc": "ok"})
	proc.finalise()
	content = out.read_text(encoding="utf-8")
	assert "\033[" not in content


def test_file_finalise_trailing_newline(tmp_path):
	out = tmp_path / "run.log"
	proc = _make_file(out)
	proc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	proc.finalise()
	content = out.read_text(encoding="utf-8")
	assert content.endswith("\n")


def test_file_finalise_noop_empty(tmp_path):
	out = tmp_path / "run.log"
	proc = _make_file(out)
	proc.finalise()
	assert not out.exists()


def test_file_finalise_oserror_silent(tmp_path):
	out = tmp_path / "run.log"
	proc = _make_file(out)
	proc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "k1"})
	with patch("builtins.open", side_effect=OSError(13, "Permission denied")):
		proc.finalise()
	assert not out.exists()


def test_file_config_defaults():
	config = FileSummaryProcessor.Config(out=Path("x.log"))
	assert config.suppress == []
	assert config.fail == list(FAIL_EVENTS)
