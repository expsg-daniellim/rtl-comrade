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
				graph.nodes[node.id] = NodeWrapper(mappings[node.module], node.id, node.config, node.ports)

		if len(errs) > 0:
			raise errs

		consumption = [ False for _ in config.edges ]
		for id, node in graph.nodes.items():
			dsts = []
			for (i, edge) in enumerate(config.edges):
				if edge.src.node == id:
					consumption[i] = True
					dsts.append(Connection(edge.src.port, graph.nodes[edge.dst.node], edge.dst.port))

			for dst in dsts:
				if dst.other_node.id not in graph.nodes:
					raise f"{dst.other_node.id} not found in graph"

			dsts.sort(key=lambda conn: conn.self_port)
			node.set_dsts(dsts)

		# TODO: Validate a src only takes one connection
		
		errs = [ f"edge {i} is not used" for (i, used) in enumerate(consumption) if not used ]
		if len(errs) > 0:
			raise errs

		return graph

	async def run(self):
		runs = [ node.run() for node in self.nodes.values() ]
		await asyncio.gather(*runs)
