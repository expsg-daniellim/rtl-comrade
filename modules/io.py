from serde import serde
import structlog

log = structlog.get_logger()
class FileReadMod:
	@serde
	class Config:
		file: str

	def __init__(self, config):
		self.file = config.file

	def run(self):
		try:
			with open(self.file, 'r') as file:
				for line in file:
					yield line
		except UnicodeDecodeError as e:
			log.fatal('invalid_unicode', reason=e.reason, invalid_slice=e.object[e.start:e.end])
		except FileNotFoundError as e:
			log.fatal('not_found')
		except IsADirectoryError as e:
			log.fatal('is_directory')
		except PermissionError as e:
			log.fatal('permission_denied')
		except OSError as e:
			log.fatal('os_error', errno=e.errno)
		except SyntaxError as e:
			log.fatal('syntax_error', filename=e.filename, lineno=e.lineno, offset=e.offset, text=e.text, end_lineno=e.end_lineno, end_offset=e.end_offset)

class StdoutMod:
	def run(self, a):
		print(a)
