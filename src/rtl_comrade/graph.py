from .config import GraphConfig
from dataclasses import dataclass
from serde.yaml import from_yaml
import asyncio

from .node import Connection, NodeWrapper
from .module import load_module_folders

@dataclass
class Graph:
	nodes: dict[str, NodeWrapper]

	def __init__(self):
		self.nodes = {}

	@staticmethod
	def from_file(path:str) -> Graph:
		config = None
		with open(path, 'r') as file:
			config = from_yaml(GraphConfig, file.read())

		# TODO: proper error handling
		if config is None:
			raise "no config read"

		return Graph.from_config(config)

	@staticmethod
	def from_config(config:GraphConfig) -> Graph:
		graph = Graph()
		errs = []

		mappings = load_module_folders(config.modules)

		for i, node in enumerate(config.nodes):
			if node.id in graph.nodes:
				errs.append(f"Node entry {i + 1} is a duplicate id")
			else:
				graph.nodes[node.id] = NodeWrapper(mappings[node.module], node.id, node.config)

		if len(errs) > 0:
			raise errs

		for id, node in graph.nodes.items():
			# TODO: make sure graph.nodes[edge.dst.node] exists
			dsts = list(map(lambda edge: Connection(edge.src.port, graph.nodes[edge.dst.node], edge.dst.port), filter(lambda edge: edge.src.node == id, config.edges)))
			dsts.sort(key=lambda conn: conn.self_port)
			node.set_dsts(dsts)
		
		# TODO: Verify that all edges are used
		#consumption = [(False, False) for _ in config.edges]
		#for i, edges in enumerate(config.edges):

		return graph

	async def run(self):
		runs = [ node.run() for node in self.nodes.values() ]
		await asyncio.gather(*runs)
