from .config import GraphConfig
from dataclasses import dataclass
from serde.yaml import from_yaml
import asyncio

from .module import load_module_folders
from .module_wrapper import Connection, ModuleWrapper
from .validation import validate_acyclic

@dataclass
class Graph:
	nodes: dict[str, ModuleWrapper]

	def __init__(self):
		self.nodes = {}

	@staticmethod
	def from_file(path:str) -> Graph:
		config = None
		with open(path, 'r') as file:
			config = from_yaml(GraphConfig, file.read())

		if config is None:
			raise ValueError("no config read")

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
				if not node.module in mappings:
					errs.append(f"Node entry {i + 1} has invalid module name {node.module}")
				graph.nodes[node.id] = ModuleWrapper(mappings[node.module], node.id, node.config, node.ports)

		if len(errs) > 0:
			# TODO: log errs
			print("\n".join(errs))
			raise AttributeError(errs[-1])

		consumption = [ False for _ in config.edges ]
		for id, node in graph.nodes.items():
			dsts = []
			for (i, edge) in enumerate(config.edges):
				if edge.src.node == id:
					if edge.dst.node not in graph.nodes:
						raise AttributeError(f"{edge.dst.node} not found in graph")

					consumption[i] = True
					dst_name = graph.nodes[edge.dst.node].get_canonical_port(edge.dst.port)
					if dst_name is None:
						raise AttributeError(f"{edge.dst.port} is not a valid port on {edge.dst.node}")

					dsts.append(Connection(edge.src.port, graph.nodes[edge.dst.node], dst_name))

			dsts.sort(key=lambda conn: conn.self_port)
			node.set_dsts(dsts)

		# TODO: Validate a src only takes one connection

		errs = [ f"edge {i} is not used" for (i, used) in enumerate(consumption) if not used ]
		if len(errs) > 0:
			# TODO: log errs
			raise Exception(errs[-1])

		if not validate_acyclic(config):
			raise Exception("graph is not acyclic")

		return graph

	async def run(self):
		runs = [ node.run() for node in self.nodes.values() ]
		await asyncio.gather(*runs)
