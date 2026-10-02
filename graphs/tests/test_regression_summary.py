"""Tests for graphs/log/regression_summary.py — ConsoleRegressionSummaryProcessor, FileRegressionSummaryProcessor."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from structlog.exceptions import DropEvent

from rtl_comrade.loader_logger import LoggingConfig, LoggingHandlerConfig
from rtl_comrade.testing import logging_handler  # noqa: F401  # pylint: disable=unused-import

LOG_DIR = Path(__file__).parent.parent / "log"
if str(LOG_DIR) not in sys.path:
	sys.path.insert(0, str(LOG_DIR))  # the plugin's `from summary import ...` resolves as it does under the logging loader
spec = importlib.util.spec_from_file_location("graphs_log_regression_summary", LOG_DIR / "regression_summary.py")
assert spec is not None
assert spec.loader is not None
mod = importlib.util.module_from_spec(spec)
sys.modules["graphs_log_regression_summary"] = mod
spec.loader.exec_module(mod)
ConsoleRegressionSummaryProcessor = mod.ConsoleRegressionSummaryProcessor
FileRegressionSummaryProcessor = mod.FileRegressionSummaryProcessor
VERDICT_COLOURS = sys.modules["summary"].VERDICT_COLOURS


def make_console():
	return ConsoleRegressionSummaryProcessor(ConsoleRegressionSummaryProcessor.Config())


def make_file(out):
	return FileRegressionSummaryProcessor(FileRegressionSummaryProcessor.Config(out=out))


def feed(proc, *events):
	for ev in events:
		proc(None, "info", dict(ev))


def builder(name="verilator"):
	return {"event": "regression_builder", "builder": name}


def mode(value="reg"):
	return {"event": "regression_builder_mode", "mode": value}


def suite(name, path):
	return {"event": "regression_suite", "suite": name, "path": Path(path)}


def passed(test_name, key, desc="ok"):
	return {"event": "parse_log_passed", "test_name": test_name, "key": key, "desc": desc}


def table_lines(proc):
	return proc.render_table().splitlines()


def test_header_and_rows_grouped_by_suite_in_suite_event_order():
	proc = make_console()
	feed(proc, builder("vcs"), mode("debug"), suite("b", "/p/b/tests.yaml"), suite("a", "/p/a/tests.yaml"), passed("t1", "a/t1#0#1"), passed("t2", "b/t2#0#1"), passed("t3", "a/t3#0#1"))
	lines = table_lines(proc)
	assert lines[:3] == ["", "Regression Results Summary", "Builder: vcs, Builder Mode: debug"]
	assert [ (line.split()[0], line.split()[1]) for line in lines[3:] ] == [("/p/b/tests.yaml", "t2"), ("/p/a/tests.yaml", "t1"), ("/p/a/tests.yaml", "t3")]


def test_row_layout_matches_rtl_buddy():
	proc = make_console()
	feed(proc, builder(), mode(), suite("a", "/p/a/tests.yaml"), passed("t1", "a/t1", desc="(nwrn=  0)"))
	assert table_lines(proc)[3] == f"{'/p/a/tests.yaml':<35} {'t1':<30} {'PASS':<8} (nwrn=  0)"


def test_same_named_test_in_two_suites_one_row_each():
	proc = make_console()
	feed(proc, suite("a", "/p/a/tests.yaml"), suite("b", "/p/b/tests.yaml"), passed("basic", "a/basic"), passed("basic", "b/basic"))
	rows = [ line.split()[:2] for line in table_lines(proc)[3:] ]
	assert rows == [["/p/a/tests.yaml", "basic"], ["/p/b/tests.yaml", "basic"]]


@pytest.mark.parametrize("key", ["zzz/t1", "t1", None])
def test_unmatched_suite_prefix_shows_na(key):
	proc = make_console()
	feed(proc, suite("a", "/p/a/tests.yaml"), passed("t1", key))
	assert table_lines(proc)[3].split()[:2] == ["NA", "t1"]


def test_missing_builder_and_mode_events_show_na():
	proc = make_console()
	feed(proc, passed("t1", "a/t1"))
	assert table_lines(proc)[2] == "Builder: NA, Builder Mode: NA"


def test_none_fields_render_na():
	proc = make_console()
	feed(proc, suite("a", "/p/a/tests.yaml"), {"event": "parse_log_passed", "test_name": None, "key": "a/x"})
	assert table_lines(proc)[3].split() == ["/p/a/tests.yaml", "NA", "PASS", "NA"]


def test_desc_truncated_to_50_characters():
	proc = make_console()
	feed(proc, suite("a", "/p/a/tests.yaml"), passed("t1", "a/t1", desc="x" * 80))
	assert table_lines(proc)[3].endswith(" " + "x" * 50)


def test_fail_row_appends_failure_count():
	proc = make_console()
	feed(proc, suite("a", "/p/a/tests.yaml"), {"event": "compile_failed", "test_name": "t1", "key": "a/t1"}, passed("t2", "a/t2"))
	lines = table_lines(proc)
	assert lines[-1] == "1 failure"
	assert "/p/a/tests.yaml" in lines[3] and "FAIL" in lines[3] and "Compile failed" in lines[3]


def test_no_failure_count_when_all_pass():
	proc = make_console()
	feed(proc, passed("t1", "a/t1"))
	assert "failure" not in proc.render_table()


def test_metadata_events_pass_through_without_rows():
	proc = make_console()
	for ev in (builder(), mode(), suite("a", "/p/a/tests.yaml")):
		assert proc(None, "info", ev) is ev
	assert len(proc.rows) == 0


def test_suppressed_verdict_still_captured():
	proc = ConsoleRegressionSummaryProcessor(ConsoleRegressionSummaryProcessor.Config(suppress=["compile_failed"]))
	with pytest.raises(DropEvent):
		proc(None, "error", {"event": "compile_failed", "test_name": "t1", "key": "a/t1"})
	assert len(proc.rows) == 1


def test_console_noop_when_no_rows(capsys):
	proc = make_console()
	feed(proc, builder(), mode(), suite("a", "/p/a/tests.yaml"))
	proc.finalise()
	assert capsys.readouterr().out == ""


def test_console_colourises_on_tty(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: True)
	proc = make_console()
	feed(proc, passed("t1", "a/t1"))
	proc.finalise()
	out = capsys.readouterr().out
	assert "Regression Results Summary" in out
	assert VERDICT_COLOURS["PASS"] in out


def test_console_plain_when_not_tty(capsys, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: False)
	proc = make_console()
	feed(proc, passed("t1", "a/t1"))
	proc.finalise()
	out = capsys.readouterr().out
	assert "Regression Results Summary" in out
	assert "\033[" not in out


def test_file_writes_plain_table(tmp_path, monkeypatch):
	monkeypatch.setattr("sys.stdout.isatty", lambda: True)
	out = tmp_path / "summary.log"
	proc = make_file(out)
	feed(proc, builder(), mode(), suite("a", "/p/a/tests.yaml"), passed("t1", "a/t1"))
	proc.finalise()
	content = out.read_text(encoding="utf-8")
	assert content == proc.render_table() + "\n"
	assert "\033[" not in content


def test_file_noop_when_no_rows(tmp_path):
	out = tmp_path / "summary.log"
	proc = make_file(out)
	feed(proc, builder(), mode())
	proc.finalise()
	assert not out.exists()


def test_file_swallows_oserror(tmp_path):
	out = tmp_path / "summary.log"
	proc = make_file(out)
	feed(proc, passed("t1", "a/t1"))
	with patch("builtins.open", side_effect=OSError(13, "Permission denied")):
		proc.finalise()
	assert not out.exists()


@pytest.mark.parametrize("processor,reference", [
	(ConsoleRegressionSummaryProcessor, "ConsoleSummaryProcessor"),
	(FileRegressionSummaryProcessor, "FileSummaryProcessor"),
])
def test_config_defaults_match_summary(processor, reference):
	assert vars(processor.Config()) == vars(getattr(sys.modules["summary"], reference).Config())


def test_processors_pass_loader_signature_validation(logging_handler):
	config = LoggingConfig(handlers=[LoggingHandlerConfig(path=Path("regression_summary.py"), name=name) for name in ("FileRegressionSummaryProcessor", "ConsoleRegressionSummaryProcessor")])
	processors, handlers = config.load(LOG_DIR)
	assert [ p.name for p in processors ] == ["FileRegressionSummaryProcessor", "ConsoleRegressionSummaryProcessor"]
	assert handlers == []
	assert not logging_handler.failure
