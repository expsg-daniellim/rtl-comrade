from pathlib import Path
from typing import Any, cast

import structlog
from serde import serde, field

from rtl_comrade.logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())


class AddMod:
	def run(self, a: int, b: int):
		return int(a) + int(b)


class ALUMod:
	id: str

	def run(self, a: int, b: int, op: int):
		if int(op) == 0:
			return int(a) + int(b)
		elif int(op) == 1:
			return int(a) - int(b)
		else:
			log.error("invalid_op", op=op)
			return None


class DirnameMod:
	def run(self, path:str|Path):
		p = Path(path)
		if p.is_file():
			return ("default", p.parent)
		if p.is_dir():
			return ("default", p)
		return ("default", p.parent)


LOG_LEVELS = {"debug", "info", "warning", "error", "critical", "fatal"}


class LoggerMod:
	@serde
	class Config:
		level:str = "info"
		event:str = "logged_value"
		mapping:dict[str, str]|str = "value"
		constants:dict[str, Any] = field(default_factory=dict)

	def __init__(self, config):
		if config.level not in LOG_LEVELS:
			log.fatal("logger_invalid_level", level=config.level, allowed=sorted(LOG_LEVELS))
		self.event = config.event
		self.constants = config.constants
		self.mapping = {config.mapping: ""} if isinstance(config.mapping, str) else config.mapping
		reserved = {"event", "exc_info", "stack_info"}
		for name in reserved:
			if name in self.mapping or name in self.constants:
				log.fatal("logger_reserved_kwarg", name=name)
		self.emit = getattr(log, config.level)

	def run(self, value:Any):
		kwargs = dict(self.constants)
		for name, path in self.mapping.items():
			resolved = value
			try:
				for part in path.split(".") if path else []:  # attribute before dict entry
					resolved = getattr(resolved, part) if hasattr(resolved, part) else resolved[part]
			except (KeyError, TypeError) as e:
				if name not in self.constants:  # a constant of the same name is the declared fallback
					log.error("logger_unresolved_field", target_event=self.event, field=name, path=path, err=str(e))
				continue
			kwargs[name] = resolved
		self.emit(self.event, **kwargs)
