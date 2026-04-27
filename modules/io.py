from serde import serde

class FileReadMod:
	@serde
	class Config:
		file: str

	def __init__(self, config):
		self.file = config.file

	def run(self):
		with open(self.file, 'r') as file:
			for line in file:
				yield line

class StdoutMod:
	def run(self, a):
		print(a)
