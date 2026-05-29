"""Logging setup and failure semantics for the harness runtime."""

import logging
from typing import Any, NoReturn
import structlog
from structlog.contextvars import merge_contextvars
from structlog.stdlib import ProcessorFormatter, LoggerFactory, BoundLogger

class HarnessLogger(BoundLogger):
	"""BoundLogger subclass that declares fatal/critical as non-returning.

	At runtime the LoggingFatalHandler raises SystemExit(1) on CRITICAL records,
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

	def __init__(self, stream=None):
		"""Initialize the handler and its failure-tracking state.

		Args:
			stream: Optional output stream for the underlying StreamHandler.

		Returns:
			None.
		"""

		super().__init__(stream)
		self.failure = False

	def emit(self, record:logging.LogRecord):
		"""Emit one log record and update failure/termination state.

		Args:
			record: Log record to emit.

		Returns:
			None.
		"""

		super().emit(record)

		if record.levelno >= logging.ERROR:
			self.failure = True

		if record.levelno >= logging.CRITICAL:
			raise SystemExit(1)

def initialise_logging(level:int = logging.INFO) -> LoggingFatalHandler:
	"""Configure stdlib logging and structlog for harness execution.

	Args:
		level: Minimum log level for the installed root handler.

		Returns:
			The installed handler used to track deferred run failure state.
	"""

	preprocessors = [ structlog.stdlib.add_log_level, structlog.stdlib.add_logger_name, structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S") ]

	handler = LoggingFatalHandler()
	handler.setLevel(level)
	handler.setFormatter(ProcessorFormatter(processor=structlog.dev.ConsoleRenderer(), foreign_pre_chain=preprocessors))

	root_logger = logging.getLogger()
	root_logger.handlers.clear()
	root_logger.addHandler(handler)
	root_logger.setLevel(level)

	structlog.configure(processors=[*preprocessors, merge_contextvars, ProcessorFormatter.wrap_for_formatter], logger_factory=LoggerFactory(), wrapper_class=BoundLogger, cache_logger_on_first_use=True)
	return handler
