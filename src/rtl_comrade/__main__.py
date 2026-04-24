import asyncio
from collections import deque
from pyventus.events import AsyncIOEventEmitter, EventEmitter, EventLinker
from inspect import signature
from serde import serde, from_dict
from asyncio import Queue

from .graph import Graph

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
	def run(self, a, b):
		yield a + b

class ModuleWrapper:
	def __init__(self, Module, config, srcs, dsts):
		# TODO: warn about config acceptance
		init_sig = signature(Module.__init__)

		if 'config' in init_sig.parameters:
			if hasattr(Module, 'Config'):
				config = from_dict(Module.Config, config)
			self.module = Module(config=config)
		else:
			self.module = Module()

		if not hasattr(self.module, 'run'):
			raise "module is not runnable"

		run_sig = signature(self.module.run)
		self.ports = list(run_sig.parameters.keys())
		self.running = False

		self.completed_queue = Queue()
		for _ in dsts:
			self.completed_queue.put(True)

	def accept(self, val, port=1):
		port_name = None
		if type(port) is str:
			port_name = port
		elif type(port) is int:
			if port - 1 < len(self.ports) and port - 1 >= 0:
				port_name = self.ports[port - 1]
			else:
				raise "invalid port type"
		else:
			raise "invalid port type"

	def run(self):
		# for val in self.module.run(*self.args):
		pass

async def run_module():
	pass

# TODO: async
# TODO: test multi-outputs
mappings = { 'fileread': FileReadMod, 'add': AddMod, 'stdout': StdoutMod }

def main() -> int:
	graph = Graph.from_file('graph.yaml')
	print(graph)

	modules = {}
	for id, node in graph.nodes.items():
		modules[id] = ModuleWrapper(mappings[node.module], node.config, node.srcs, node.dsts)

	return 0

if __name__ == '__main__':
	raise SystemExit(main())
