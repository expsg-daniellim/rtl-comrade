from serde import serde
import structlog

log = structlog.get_logger()
class FileReadMod:
	@serde
	class Config:
		file: str

	def __init__(self, id, config):
		self.id = id
		self.file = config.file

	def run(self):
		try:
			with open(self.file, 'r') as file:
				for line in file:
					yield line
		except OSError as e:
			log.fatal('%s.file.not_found', self.id)
		except UnicodeDecodeError as e:
			log.fatal('%s.file.invalid_unicode', self.id, reason=e.reason, invalid_slice=e.object[e.start:e.end])

class StdoutMod:
	def run(self, a):
		print(a)
