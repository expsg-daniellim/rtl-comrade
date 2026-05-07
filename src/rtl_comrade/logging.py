from dataclasses import dataclass
import logging
import structlog
from structlog.stdlib import ProcessorFormatter, LoggerFactory, BoundLogger

@dataclass
class LoggingFatalHandler(logging.StreamHandler):
	failure:bool = False

	def emit(self, record:logging.LogRecord):
		super().emit(record)
		if record.levelno >= logging.CRITICAL:
			raise SystemExit(1)
		elif record.levelno >= logging.ERROR:
			failure = True

def initialise_logging(level:int = logging.INFO) -> LoggingFatalHandler:
	preprocessors = [ structlog.stdlib.add_log_level, structlog.stdlib.add_logger_name ]

	handler = LoggingFatalHandler()
	handler.setFormatter(ProcessorFormatter(processor=structlog.dev.ConsoleRenderer(), foreign_pre_chain=preprocessors))

	root_logger = logging.getLogger()
	root_logger.handlers.clear()
	root_logger.addHandler(handler)
	root_logger.setLevel(level)

	structlog.configure(processors=[*preprocessors, ProcessorFormatter.wrap_for_formatter], logger_factory=LoggerFactory(), wrapper_class=BoundLogger, cache_logger_on_first_use=True)
	return handler
