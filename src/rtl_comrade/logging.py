from dataclasses import dataclass
import logging
import structlog
from structlog.contextvars import merge_contextvars
from structlog.stdlib import ProcessorFormatter, LoggerFactory, BoundLogger

class LoggingFatalHandler(logging.StreamHandler):
	def __init__(self, stream=None):
		super().__init__(stream)
		self.failure = False

	def emit(self, record:logging.LogRecord):
		super().emit(record)

		if record.levelno >= logging.ERROR:
			self.failure = True

		if record.levelno >= logging.CRITICAL:
			raise SystemExit(1)

def initialise_logging(level:int = logging.INFO) -> LoggingFatalHandler:
	preprocessors = [ structlog.stdlib.add_log_level, structlog.stdlib.add_logger_name ]

	handler = LoggingFatalHandler()
	handler.setLevel(level)
	handler.setFormatter(ProcessorFormatter(processor=structlog.dev.ConsoleRenderer(), foreign_pre_chain=preprocessors))

	root_logger = logging.getLogger()
	root_logger.handlers.clear()
	root_logger.addHandler(handler)
	root_logger.setLevel(level)

	structlog.configure(processors=[*preprocessors, merge_contextvars, ProcessorFormatter.wrap_for_formatter], logger_factory=LoggerFactory(), wrapper_class=BoundLogger, cache_logger_on_first_use=True)
	return handler
