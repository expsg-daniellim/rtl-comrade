from .config import GraphConfig, GraphConfigEdge
from dataclasses import dataclass
from serde.yaml import from_yaml
import asyncio

from .module import Connection, ModuleWrapper

@dataclass
class Graph:
	modules: dict[str, ModuleWrapper]

	def __init__(self):
		self.modules = {}

	@staticmethod
	def from_file(path:str, mappings:dict) -> Graph:
		config = None
		with open(path, 'r') as file:
			config = from_yaml(GraphConfig, file.read())

		# TODO: proper error handling
		if config is None:
			raise "no config read"

		return Graph.from_config(config, mappings)

	@staticmethod
	def from_config(config:GraphConfig, mappings:dict) -> Graph:
		graph = Graph()
		errs = []
		# TODO: expand implicit ports in edges

		for i, node in enumerate(config.nodes):
			if node.id in graph.modules:
				errs.append(f"Node entry {i + 1} is a duplicate id")
			else:
				graph.modules[node.id] = ModuleWrapper(mappings[node.module], node.id, node.config)

		if len(errs) > 0:
			raise errs

		for id, module in graph.modules.items():
			dsts = list(map(lambda edge: Connection(edge.src.port, graph.modules[edge.dst.node], edge.dst.port), filter(lambda edge: edge.src.node == id, config.edges)))
			dsts.sort(key=lambda conn: conn.self_port)
			module.set_dsts(dsts)
		
		# TODO: Verify that all edges are used
		#consumption = [(False, False) for _ in config.edges]
		#for i, edges in enumerate(config.edges):

		return graph

	async def run(self):
		runs = [ module.run() for module in self.modules.values() ]
		await asyncio.gather(*runs)
