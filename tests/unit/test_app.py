"""Unit tests for app.py — App CLI, config discovery, and error handling."""

import inspect
import logging
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import click
import pytest
import structlog
import typer
from click.exceptions import NoArgsIsHelpError
from serde import SerdeError
from typer.testing import CliRunner
from yaml.error import Mark, MarkedYAMLError
from yaml.reader import ReaderError

from rtl_comrade.app import (
	DEFAULT_RTL_COMRADE_CONFIG_NAME,
	App,
	CommandConfig,
	RtlComradeConfig,
	search_for_config,
)
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.loader_logger import LoggingPlugin

MINIMAL_CONFIG_YAML = "commands:\n  run:\n    path: graphs/test.yaml\n"
MINIMAL_CONFIG = RtlComradeConfig(commands={"run": CommandConfig(path=Path("graphs/test.yaml"))})

runner = CliRunner()


def _mock_config():
	m = MagicMock(spec=GraphConfig)
	m.sig = inspect.Signature([])
	return m


@pytest.fixture(autouse=True)
def reset_logging():
	yield
	root = logging.getLogger()
	root.handlers.clear()
	root.setLevel(logging.WARNING)
	structlog.reset_defaults()


def _make_app(argv=None, config=None):
	with patch("rtl_comrade.app.search_for_config", return_value=config or MINIMAL_CONFIG), \
		 patch("rtl_comrade.app.GraphConfig.from_file", return_value=_mock_config()), \
		 patch("rtl_comrade.app.Graph.construct_run", side_effect=lambda config, setup_logging, cleanup: cleanup), \
		 patch.object(sys, "argv", argv or ["rtl-comrade"]):
		return App()


# ---------------------------------------------------------------------------
# search_for_config
# ---------------------------------------------------------------------------


def test_search_finds_config_in_given_dir(tmp_path):
	(tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
	assert result is not None
	assert result.commands["run"].path == Path("graphs/test.yaml")


def test_search_ascends_to_parent_dir(tmp_path):
	child = tmp_path / "child"
	child.mkdir()
	(tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, child)
	assert result is not None
	assert "run" in result.commands


def test_search_stops_at_git_root_when_no_config(tmp_path):
	(tmp_path / ".git").mkdir()
	child = tmp_path / "child"
	child.mkdir()
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, child)
	assert result is None


def test_search_finds_config_at_git_root(tmp_path):
	(tmp_path / ".git").mkdir()
	(tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
	assert result is not None


def test_search_with_file_path_matching_name(tmp_path):
	f = tmp_path / "custom.yaml"
	f.write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config("custom.yaml", f)
	assert result is not None


def test_search_with_file_path_not_matching_name(tmp_path):
	f = tmp_path / "other.yaml"
	f.write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config("custom.yaml", f)
	assert result is None


def test_search_custom_name_does_not_match_default(tmp_path):
	(tmp_path / "custom.yaml").write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
	assert result is None


def test_search_config_help_field_parsed(tmp_path):
	yaml = "commands:\n  run:\n    path: g.yaml\n    help: 'Run the ALU graph'\n"
	(tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(yaml)
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
	assert result is not None
	assert result.commands["run"].help == "Run the ALU graph"


def test_search_sets_relative_path_to_containing_dir(tmp_path):
	(tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
	assert result is not None
	assert result.relative_path == tmp_path


def test_search_ascended_sets_relative_path_to_parent_dir(tmp_path):
	child = tmp_path / "child"
	child.mkdir()
	(tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, child)
	assert result is not None
	assert result.relative_path == tmp_path


def test_search_file_path_match_sets_relative_path_to_file(tmp_path):
	f = tmp_path / "custom.yaml"
	f.write_text(MINIMAL_CONFIG_YAML)
	result = search_for_config("custom.yaml", f)
	assert result is not None
	assert result.relative_path == f


# ---------------------------------------------------------------------------
# App — startup
# ---------------------------------------------------------------------------


def test_app_config_not_found_exits():
	with patch("rtl_comrade.app.search_for_config", return_value=None), \
		 patch.object(sys, "argv", ["rtl-comrade"]):
		with pytest.raises(typer.Exit):
			App()


def test_app_logging_level_info_by_default():
	_make_app()
	assert logging.getLogger().level == logging.INFO


def test_app_logging_level_debug():
	_make_app(argv=["rtl-comrade", "--level", "debug"])
	assert logging.getLogger().level == logging.DEBUG


def test_app_logging_level_warning():
	_make_app(argv=["rtl-comrade", "--level", "warning"])
	assert logging.getLogger().level == logging.WARNING


def test_app_custom_config_file_loaded(tmp_path, monkeypatch):
	(tmp_path / ".git").mkdir()
	(tmp_path / "custom.yaml").write_text(
		"commands:\n  mycmd:\n    path: my_graph.yaml\n"
	)
	monkeypatch.chdir(tmp_path)
	with patch.object(sys, "argv", ["rtl-comrade", "--config-file", "custom.yaml"]), \
		 patch("rtl_comrade.app.GraphConfig.from_file", return_value=_mock_config()) as mock_from_file, \
		 patch("rtl_comrade.app.Graph.construct_run", side_effect=lambda config, setup_logging, cleanup: cleanup):
		App()
	mock_from_file.assert_called_once_with(tmp_path / "my_graph.yaml")


# ---------------------------------------------------------------------------
# App — subcommand dispatch and exit codes
# ---------------------------------------------------------------------------


def test_app_help_exits_0():
	app = _make_app()
	result = runner.invoke(app.app, ["--help"])
	assert result.exit_code == 0


def test_app_subcommand_exits_0_on_success():
	app = _make_app()
	result = runner.invoke(app.app, ["run"])
	assert result.exit_code == 0


def test_app_subcommand_exits_1_on_graph_failure():
	app = _make_app()
	app.handler.failure = True
	result = runner.invoke(app.app, ["run"])
	assert result.exit_code == 1


def test_app_subcommand_calls_graph_from_file():
	with patch("rtl_comrade.app.GraphConfig.from_file", return_value=_mock_config()) as mock_from_file, \
		 patch("rtl_comrade.app.Graph.construct_run", side_effect=lambda config, setup_logging, cleanup: cleanup), \
		 patch("rtl_comrade.app.search_for_config", return_value=MINIMAL_CONFIG), \
		 patch.object(sys, "argv", ["rtl-comrade"]):
		App()
	mock_from_file.assert_called_once_with(Path("graphs/test.yaml"))


def test_app_unknown_subcommand_exits_nonzero():
	app = _make_app()
	result = runner.invoke(app.app, ["nonexistent"])
	assert result.exit_code != 0


# ---------------------------------------------------------------------------
# App.main — no-subcommand branch (lines 80-81)
# ---------------------------------------------------------------------------


def test_app_no_subcommand_with_option_shows_help_and_exits_0():
	app = _make_app()
	result = runner.invoke(app.app, ["--config-file", "dummy.yaml"])
	assert result.exit_code == 0


# ---------------------------------------------------------------------------
# App.run() — exception handling and exit codes (lines 84-104)
# ---------------------------------------------------------------------------


def test_run_returns_0_on_normal_exit():
	app = _make_app()
	with patch.object(app, "app", return_value=None):
		assert app.run() == 0


def test_run_no_args_is_help_error_returns_0():
	app = _make_app()
	ctx = click.Context(click.Command("_"))
	with patch.object(app, "app", side_effect=NoArgsIsHelpError(ctx)):
		assert app.run() == 0


def test_run_typer_exit_returns_exit_code():
	app = _make_app()
	with patch.object(app, "app", side_effect=typer.Exit(code=2)):
		assert app.run() == 2


def test_run_typer_abort_returns_1():
	app = _make_app()
	with patch.object(app, "app", side_effect=typer.Abort()):
		assert app.run() == 1


def test_run_missing_parameter_logs_error_and_returns_exit_code():
	app = _make_app()
	exc = click.MissingParameter(param_hint="--foo", param_type="option")
	with patch.object(app, "app", side_effect=exc):
		code = app.run()
	assert code == exc.exit_code
	assert app.handler.failure


def test_run_bad_parameter_logs_error_and_returns_exit_code():
	app = _make_app()
	exc = click.BadParameter("bad value", param_hint="--bar")
	with patch.object(app, "app", side_effect=exc):
		code = app.run()
	assert code == exc.exit_code
	assert app.handler.failure


def test_run_bad_option_usage_logs_error_and_returns_exit_code():
	app = _make_app()
	exc = click.BadOptionUsage("--baz", "Unknown option: --baz")
	with patch.object(app, "app", side_effect=exc):
		code = app.run()
	assert code == exc.exit_code
	assert app.handler.failure


def test_run_usage_error_logs_error_and_returns_exit_code():
	app = _make_app()
	exc = click.UsageError("Something wrong")
	with patch.object(app, "app", side_effect=exc):
		code = app.run()
	assert code == exc.exit_code
	assert app.handler.failure


# ---------------------------------------------------------------------------
# App.__init__ — Graph.from_file exception handling (lines 78-100)
# ---------------------------------------------------------------------------


def _make_app_raises(exc):
	with patch("rtl_comrade.app.search_for_config", return_value=MINIMAL_CONFIG), \
		 patch.object(sys, "argv", ["rtl-comrade"]), \
		 patch("rtl_comrade.app.GraphConfig.from_file", side_effect=exc):
		App()


def test_from_file_unicode_decode_fatal():
	exc = UnicodeDecodeError('utf-8', b'\x80', 0, 1, 'invalid start byte')
	with pytest.raises(typer.Exit):
		_make_app_raises(exc)


def test_from_file_not_found_fatal():
	with pytest.raises(typer.Exit):
		_make_app_raises(FileNotFoundError())


def test_from_file_is_directory_fatal():
	with pytest.raises(typer.Exit):
		_make_app_raises(IsADirectoryError())


def test_from_file_permission_error_fatal():
	with pytest.raises(typer.Exit):
		_make_app_raises(PermissionError())


def test_from_file_os_error_fatal():
	with pytest.raises(typer.Exit):
		_make_app_raises(OSError(5, 'Input/output error'))


def test_from_file_serde_error_fatal():
	with pytest.raises(typer.Exit):
		_make_app_raises(SerdeError('bad schema'))


def test_from_file_marked_yaml_error_with_mark_fatal():
	mark = Mark('test.yaml', 5, 2, 4, None, 0)
	exc = MarkedYAMLError('ctx', None, 'bad yaml', mark)
	with pytest.raises(typer.Exit):
		_make_app_raises(exc)


def test_from_file_reader_error_fatal():
	exc = ReaderError('test', 0, b'\x80', 'utf-8', 'invalid character')
	with pytest.raises(typer.Exit):
		_make_app_raises(exc)


# ---------------------------------------------------------------------------
# App.setup_logging — install resolved processor chain and custom handlers
# ---------------------------------------------------------------------------


def _spec(plugin):
	return LoggingPlugin(plugin=plugin, config={}, relative_path=Path(), name="x")


def test_setup_logging_processors_sets_render_and_formatter():
	from structlog.stdlib import ProcessorFormatter
	app = _make_app()
	app.handler.render = False  # start from the opposite state
	app.setup_logging([_spec(structlog.dev.ConsoleRenderer())], [], include_default=False)
	assert app.handler.render is True
	assert isinstance(app.handler.formatter, ProcessorFormatter)


def test_setup_logging_include_default_appends_console_renderer():
	# include_default with no custom processors still yields a rendering chain (the terminal ConsoleRenderer).
	app = _make_app()
	app.handler.render = False
	app.setup_logging([], [], include_default=True)
	assert app.handler.render is True
	assert any(isinstance(p, structlog.dev.ConsoleRenderer) for p in app.handler.formatter.processors)


def test_setup_logging_empty_processors_disables_render():
	app = _make_app()
	app.handler.render = True
	prev_formatter = app.handler.formatter
	app.setup_logging([], [], include_default=False)
	assert app.handler.render is False
	# With no terminal renderer the formatter is left untouched (no rebuild).
	assert app.handler.formatter is prev_formatter


def test_setup_logging_appends_handlers_to_root():
	app = _make_app()
	custom = logging.Handler()
	before = list(app.root_logger.handlers)
	app.setup_logging([], [_spec(custom)], include_default=True)
	assert custom in app.root_logger.handlers
	assert app.root_logger.handlers[: len(before)] == before


# ---------------------------------------------------------------------------
# App.cleanup — finalise the run's processors and handlers
# ---------------------------------------------------------------------------


class _CountingProcessor:
	def __init__(self):
		self.finalised = False

	def __call__(self, logger, method_name, event_dict):
		return event_dict

	def finalise(self):
		self.finalised = True


class _FinaliseHandler(logging.Handler):
	def __init__(self):
		super().__init__()
		self.finalised = False

	def finalise(self):
		self.finalised = True


def test_setup_logging_stores_constructed_chain():
	app = _make_app()
	proc = _CountingProcessor()
	app.setup_logging([_spec(proc)], [], include_default=True)
	# The store is the constructed chain — the user processor (the live instance in the formatter) plus the terminal ConsoleRenderer.
	assert proc in app.processors
	assert proc in app.handler.formatter.processors
	assert any(isinstance(p, structlog.dev.ConsoleRenderer) for p in app.processors)


def test_cleanup_finalises_processors():
	app = _make_app()
	proc = _CountingProcessor()
	app.setup_logging([_spec(proc)], [], include_default=True)
	app.cleanup()
	assert proc.finalised is True


def test_cleanup_skips_processor_without_finalise():
	app = _make_app()
	def proc(logger, method_name, event_dict):
		return event_dict
	app.setup_logging([_spec(proc)], [], include_default=True)
	app.cleanup()  # a processor with no finalise is skipped, not an error


def test_cleanup_skips_non_callable_finalise():
	app = _make_app()
	class _BadProcessor:
		finalise = "not_a_function"
		def __call__(self, logger, method_name, event_dict):
			return event_dict
	class _BadHandler(logging.Handler):
		finalise = "not_a_function"
	app.setup_logging([_spec(_BadProcessor())], [_spec(_BadHandler())], include_default=True)
	app.cleanup()  # a non-callable finalise attribute is ignored, not invoked


def test_cleanup_finalises_processors_and_handlers_before_failure_check():
	app = _make_app()
	proc = _CountingProcessor()
	handler = _FinaliseHandler()
	app.setup_logging([_spec(proc)], [_spec(handler)], include_default=True)
	app.handler.failure = True
	# Finalisation runs before the failure check, so both flush even though cleanup then exits non-zero.
	with pytest.raises(typer.Exit):
		app.cleanup()
	assert proc.finalised is True
	assert handler.finalised is True
