import asyncio
from serde import serde

from .graph import Graph

# Test modules (TODO: replace with proper dynamic import)
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

class AddMod:
	def run(self, a:int, b:int):
		return int(a) + int(b)

async def run_module():
	pass

# TODO: async
# TODO: test multi-outputs
mappings = { 'fileread': FileReadMod, 'add': AddMod, 'stdout': StdoutMod }

def main() -> int:
	graph = Graph.from_file('graph.yaml', mappings)
	asyncio.run(graph.run())

	return 0

if __name__ == '__main__':
	raise SystemExit(main())
