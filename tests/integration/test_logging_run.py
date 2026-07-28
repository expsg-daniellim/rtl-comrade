"""Integration tests: per-graph custom logging through the real
Graph.construct_run → LoggingConfig.load → App.setup_logging → node-run path.

These build a real App (so App.setup_logging is exercised, not a stub) and run a
graph whose module emits log events, then assert the effect of the configured
processors and Handler-type entries.
"""

import inspect
import io
import logging
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import structlog
import typer
from structlog.contextvars import bind_contextvars, unbind_contextvars

from rtl_comrade.app import App, CommandConfig, RtlComradeConfig
from rtl_comrade.config import GraphConfigNode, GraphConfigNodePlugin
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph
from rtl_comrade.loader_logger import LoggingHandlerConfig, LoggingConfig
from rtl_comrade.loader_plugin import PluginFileConfig
from rtl_comrade.loader_utils import import_plugin_file

_MINIMAL_CONFIG = RtlComradeConfig(commands={"run": CommandConfig(path=Path("g.yaml"))})


@pytest.fixture(autouse=True)
def reset_logging():
	yield
	root = logging.getLogger()
	root.handlers.clear()
	root.setLevel(logging.WARNING)
	structlog.reset_defaults()


def _mock_graph_config():
	m = MagicMock(spec=GraphConfig)
	m.sig = inspect.Signature([])
	return m


def _make_app(stream):
	# Build a real App but stub config discovery and graph loading; capture output on `stream`.
	with patch("rtl_comrade.app.search_for_config", return_value=_MINIMAL_CONFIG), \
		 patch("rtl_comrade.app.GraphConfig.from_file", return_value=_mock_graph_config()), \
		 patch("rtl_comrade.app.Graph.construct_run", side_effect=lambda config, setup_logging, cleanup: cleanup), \
		 patch.object(sys, "argv", ["rtl-comrade"]):
		app = App()
	# Redirect the harness handler's stream to the capture buffer.
	app.handler.setStream(stream)
	return app


def _write(tmp_path, name, src):
	f = tmp_path / name
	f.write_text(textwrap.dedent(src))
	return f


def _pfc(path):
	return PluginFileConfig(name=None, file=Path(path), type_=None, plugins=None)


def _logging_module(tmp_path, *, level="info", event="hello", with_field=False):
	field = ", key='val'" if with_field else ""
	return _write(tmp_path, "mods.py", f"""\
		import structlog
		log = structlog.get_logger()

		class Emit:
			def run(self):
				log.{level}('{event}'{field})
				return None
	""")


def _run(config, app):
	Graph.construct_run(config, app.setup_logging, app.cleanup)()


# ---------------------------------------------------------------------------
# Processor happy path (include_default: true) — processor transforms event,
# ConsoleRenderer remains terminal.
# ---------------------------------------------------------------------------


def test_processor_function_runs_before_console_renderer(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _logging_module(tmp_path, event="base_event")
	proc = _write(tmp_path, "proc.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		def add_tag(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
			event_dict['tag'] = 'INJECTED'
			return event_dict
	""")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="emit", module=GraphConfigNodePlugin(name="emit"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(handlers=[LoggingHandlerConfig(path=proc, name="add_tag")], include_default=True),
	)
	_run(config, app)
	out = stream.getvalue()
	assert "base_event" in out
	assert "INJECTED" in out  # processor-injected field rendered by ConsoleRenderer
	assert app.handler.render is True


# ---------------------------------------------------------------------------
# include_default: false — last processor is the terminal -> str renderer.
# ---------------------------------------------------------------------------


def test_include_default_false_terminal_str_processor_renders(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _logging_module(tmp_path, event="evt_x")
	proc = _write(tmp_path, "proc.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping

		def render(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> str:
			return 'RENDERED:' + str(event_dict.get('event'))
	""")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="emit", module=GraphConfigNodePlugin(name="emit"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(handlers=[LoggingHandlerConfig(path=proc, name="render")], include_default=False),
	)
	_run(config, app)
	out = stream.getvalue()
	assert "RENDERED:evt_x" in out
	assert app.handler.render is True


# ---------------------------------------------------------------------------
# DropEvent suppression — processor raises DropEvent; event reaches neither the
# terminal renderer nor any later processor in the chain.
# ---------------------------------------------------------------------------


def test_drop_event_suppresses_output(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _logging_module(tmp_path, event="should_be_dropped")
	proc = _write(tmp_path, "proc.py", """\
		from __future__ import annotations
		from typing import Any
		from collections.abc import MutableMapping
		from structlog.exceptions import DropEvent

		def drop(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
			raise DropEvent

		def later(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
			event_dict['reached_later'] = True
			return event_dict
	""")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="emit", module=GraphConfigNodePlugin(name="emit"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(
			handlers=[
				LoggingHandlerConfig(path=proc, name="drop"),
				LoggingHandlerConfig(path=proc, name="later"),
			],
			include_default=True,
		),
	)
	_run(config, app)
	out = stream.getvalue()
	assert "should_be_dropped" not in out
	assert "reached_later" not in out  # later processor never ran


# ---------------------------------------------------------------------------
# Failure semantics preserved when render=False (no processors, include_default
# false) — an ERROR still flips failure and cleanup raises typer.Exit(1).
# ---------------------------------------------------------------------------


def test_failure_preserved_when_render_false(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _logging_module(tmp_path, level="error", event="boom")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="emit", module=GraphConfigNodePlugin(name="emit"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(handlers=[], include_default=False),
	)
	with pytest.raises(typer.Exit):
		_run(config, app)
	assert app.handler.render is False
	# The module's ERROR event is emitted after render is disabled, so nothing of it renders;
	# only the load-time no_renderers warning (emitted before setup_logging) may appear.
	assert "boom" not in stream.getvalue()
	assert app.handler.failure is True


# ---------------------------------------------------------------------------
# Handler-type entry happy path — a custom logging.Handler appended to root sees
# the DEBUG..ERROR records.
# ---------------------------------------------------------------------------


def test_custom_handler_receives_records(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _logging_module(tmp_path, event="seen_by_handler")
	hf = _write(tmp_path, "h.py", """\
		import logging

		class CaptureHandler(logging.Handler):
			records = []
			def emit(self, record):
				CaptureHandler.records.append(record.msg)
	""")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="emit", module=GraphConfigNodePlugin(name="emit"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(handlers=[LoggingHandlerConfig(path=hf, name="CaptureHandler")], include_default=True),
	)
	_run(config, app)
	# Reach into the loaded module to read the captured records.
	loaded = import_plugin_file(hf, None, "logging")
	unbind_contextvars("plugin", "file")
	# The custom handler observed at least one record carrying the raw event dict as msg.
	assert any(
		isinstance(m, dict) and m.get("event") == "seen_by_handler"
		for m in loaded.CaptureHandler.records
	)


# ---------------------------------------------------------------------------
# CRITICAL-ordering constraint — a custom Handler-type entry never observes a
# CRITICAL record because the harness handler raises typer.Exit(1) first.
# ---------------------------------------------------------------------------


def test_custom_handler_never_sees_critical(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _write(tmp_path, "mods.py", """\
		import structlog
		log = structlog.get_logger()

		class Fatal:
			def run(self):
				log.info('before_fatal')
				log.critical('the_fatal_event')
				return None
	""")
	hf = _write(tmp_path, "h.py", """\
		import logging

		class CritWatch(logging.Handler):
			seen = []
			def emit(self, record):
				CritWatch.seen.append((record.levelno, record.msg))
	""")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="fatal", module=GraphConfigNodePlugin(name="fatal"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(handlers=[LoggingHandlerConfig(path=hf, name="CritWatch")], include_default=True),
	)
	with pytest.raises(typer.Exit):
		_run(config, app)

	loaded = import_plugin_file(hf, None, "logging")
	unbind_contextvars("plugin", "file")
	# It saw the INFO record but never a CRITICAL one.
	assert any(lvl == logging.INFO for lvl, _ in loaded.CritWatch.seen)
	assert not any(lvl >= logging.CRITICAL for lvl, _ in loaded.CritWatch.seen)


# ---------------------------------------------------------------------------
# merge_contextvars applied to a foreign stdlib log — a bound contextvar is
# merged into a record emitted by a plain stdlib logger (the foreign pre-chain).
# ---------------------------------------------------------------------------


def test_merge_contextvars_on_foreign_stdlib_log(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _write(tmp_path, "mods.py", """\
		import logging
		stdlib_log = logging.getLogger('foreign.lib')

		class Emit:
			def run(self):
				stdlib_log.warning('foreign message')
				return None
	""")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="emit", module=GraphConfigNodePlugin(name="emit"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(handlers=[], include_default=True),
	)
	bind_contextvars(merged_key="MERGED_VALUE")
	try:
		_run(config, app)
	finally:
		unbind_contextvars("merged_key")
	out = stream.getvalue()
	assert "foreign message" in out
	assert "MERGED_VALUE" in out  # contextvar merged into the foreign record


# ---------------------------------------------------------------------------
# Empty-handlers-list warn under include_default: false — LoggingConfig.load emits the
# no_renderers warning; the run still completes (warning, not failure).
# ---------------------------------------------------------------------------


def test_empty_handlers_include_default_false_warns_no_renderers(tmp_path):
	stream = io.StringIO()
	app = _make_app(stream)
	mods = _logging_module(tmp_path, event="quiet")
	config = GraphConfig(
		nodes=[GraphConfigNode(id="emit", module=GraphConfigNodePlugin(name="emit"))],
		edges=[],
		modules=[_pfc(mods)],
		contracts=[],
		logging=LoggingConfig(handlers=[], include_default=False),
	)
	_run(config, app)
	# Nothing renders (render flag off); failure is not set by a warning.
	assert app.handler.render is False
	assert app.handler.failure is False
