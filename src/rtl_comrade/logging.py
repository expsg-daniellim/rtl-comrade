"""Logging setup and failure semantics for the harness runtime."""

import logging
from typing import Any, NoReturn
import structlog
from structlog.contextvars import merge_contextvars
from structlog.exceptions import DropEvent
from structlog.stdlib import ProcessorFormatter, LoggerFactory, BoundLogger
import typer

class HarnessLogger(BoundLogger):
	"""BoundLogger subclass that declares fatal/critical as non-returning.

	At runtime the LoggingFatalHandler raises typer.Exit(1) on CRITICAL records,
	so these methods never return. The raise after super() is unreachable in
	practice but satisfies ty's control-flow analysis.
	"""

	def fatal(self, *args:Any, event:str|None = None, **kw:Any) -> NoReturn:  # pragma: no cover
		super().fatal(event, *args, **kw)
		raise AssertionError('unreachable')

	def critical(self, *args:Any, event:str|None = None, **kw:Any) -> NoReturn:  # pragma: no cover
		super().critical(event, *args, **kw)
		raise AssertionError('unreachable')

class LoggingFatalHandler(logging.StreamHandler):
	"""Stream handler that turns error severity into harness failure semantics.

	Attributes:
		failure: Whether any error-level or higher record has been emitted.
	"""

	def __init__(self, stream=None, render:bool = True):
		"""Initialise the handler and its failure-tracking state.

		Args:
			stream: Optional output stream for the underlying StreamHandler.
			render: Whether to write records; gated by include_default.

		Returns:
			None.
		"""

		super().__init__(stream)
		self.failure = False
		self.render = render

	def emit(self, record:logging.LogRecord):
		"""Emit one log record and update failure/termination state.

		Args:
			record: Log record to emit.

		Returns:
			None.
		"""

		if self.render:
			try:
				super().emit(record)  # format() may raise DropEvent before any write
			except DropEvent:
				pass

		if record.levelno >= logging.ERROR:
			self.failure = True

		if record.levelno >= logging.CRITICAL:
			raise typer.Exit(1)

def initialise_logging(level:int = logging.INFO) -> tuple[LoggingFatalHandler, logging.Logger]:
	"""Configure stdlib logging and structlog for harness execution.

	Args:
		level: Minimum log level for the installed root handler.

		Returns:
			The installed handler (deferred-failure tracking) and the root logger. The shared
			preprocessor chain is retrievable from ``structlog.get_config()["processors"]``.
	"""

	preprocessors = [ merge_contextvars, structlog.stdlib.add_log_level, structlog.stdlib.add_logger_name, structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S") ]

	handler = LoggingFatalHandler()
	handler.setLevel(level)
	handler.setFormatter(ProcessorFormatter(processor=structlog.dev.ConsoleRenderer(), foreign_pre_chain=preprocessors))

	root_logger = logging.getLogger()
	root_logger.handlers.clear()
	root_logger.addHandler(handler)
	root_logger.setLevel(level)

	structlog.configure(processors=[*preprocessors, ProcessorFormatter.wrap_for_formatter], logger_factory=LoggerFactory(), wrapper_class=BoundLogger, cache_logger_on_first_use=True)
	return (handler, root_logger)
