from pathlib import Path
from typing import cast

from serde import serde
import structlog

from rtl_comrade.logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())


class FileReadMod:
	@serde
	class Config:
		file: Path

	def __init__(self, config):
		self.file = config.file

	def run(self):
		try:
			with open(self.file, "r", encoding="utf-8") as file:
				for line in file:
					yield ("default", line)
		except UnicodeDecodeError as e:
			log.fatal("invalid_unicode", file=self.file, reason=e.reason, invalid_slice=e.object[e.start : e.end].decode(encoding=e.encoding or "utf-8", errors="replace"))
		except FileNotFoundError:
			log.fatal("not_found", file=self.file)
		except IsADirectoryError:
			log.fatal("is_directory", file=self.file)
		except PermissionError:
			log.fatal("permission_denied", file=self.file)
		except OSError as e:
			log.fatal("os_error", file=self.file, err=e.strerror, errno=e.errno)


class StdoutMod:
	def run(self, a):
		print(a)
