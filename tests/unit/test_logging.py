"""Unit tests for logging.py — LoggingFatalHandler render flag and failure semantics."""

import io
import logging

import pytest
import typer
from structlog.exceptions import DropEvent

from rtl_comrade.logging import LoggingFatalHandler


# ---------------------------------------------------------------------------
# LoggingFatalHandler — render flag and DropEvent suppression
# ---------------------------------------------------------------------------


def _record(level=logging.INFO, msg="evt"):
	return logging.LogRecord("test", level, __file__, 1, msg, None, None)


def test_emit_render_false_skips_write_but_tracks_failure():
	# render=False: nothing is written, but an ERROR still sets failure.
	stream = io.StringIO()
	h = LoggingFatalHandler(stream=stream, render=False)
	h.setFormatter(logging.Formatter("%(message)s"))
	h.emit(_record(logging.ERROR, "boom"))
	assert stream.getvalue() == ""
	assert h.failure is True


def test_emit_render_false_critical_still_exits():
	# render=False: failure/exit tracking still runs; CRITICAL raises typer.Exit.
	h = LoggingFatalHandler(stream=io.StringIO(), render=False)
	with pytest.raises(typer.Exit):
		h.emit(_record(logging.CRITICAL, "fatal"))


def test_emit_render_true_writes():
	stream = io.StringIO()
	h = LoggingFatalHandler(stream=stream, render=True)
	h.setFormatter(logging.Formatter("%(message)s"))
	h.emit(_record(logging.INFO, "hello"))
	assert "hello" in stream.getvalue()
	assert h.failure is False


def test_emit_drop_event_suppressed():
	# A formatter that raises DropEvent suppresses the write without surfacing an error.
	class DroppingFormatter(logging.Formatter):
		def format(self, record):
			raise DropEvent

	stream = io.StringIO()
	h = LoggingFatalHandler(stream=stream, render=True)
	h.setFormatter(DroppingFormatter())
	h.emit(_record(logging.INFO, "dropme"))
	assert stream.getvalue() == ""
	assert h.failure is False
