from .config import GraphConfig
from dataclasses import dataclass
from serde.yaml import from_yaml
import asyncio

from .contract_default import DefaultContract
from .loader import load_folders
from .module import Connection, ModuleWrapper
from .validation import validate_acyclic, validate_no_static_deadlock

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

		module_mappings = load_folders(config.modules)
		contract_mappings = load_folders(config.contracts)

		for i, node in enumerate(config.nodes):
			if node.id in graph.nodes:
				errs.append(f"Node entry {i + 1} is a duplicate id")
			else:
				has_error = False
				if not node.module in module_mappings:
					errs.append(f"Node entry {i + 1} has invalid module name {node.module}")
					has_error = True

				if node.contract != '' and not node.contract in contract_mappings:
					errs.append(f"Node entry {i + 1} has invalid contract name {node.contract}")
					has_error = True

				if not has_error:
					contract = contract_mappings[node.contract] if node.contract != '' else DefaultContract
					graph.nodes[node.id] = ModuleWrapper(id=node.id, Module=module_mappings[node.module], config=node.config, Contract=contract, contract_config=node.contract_config)

		if len(errs) > 0:
			# TODO: log errs
			print("\n".join(errs))
			raise AttributeError(errs[-1])

		source_tracker = {} # Verify each dst only has one source
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

					# Source tracking
					key = (edge.dst.node, dst_name)
					if not key in source_tracker:
						source_tracker[key] = 1
					else:
						source_tracker[key] += 1

			dsts.sort(key=lambda conn: conn.self_port)
			node.set_dsts(dsts)

		errs = [ f"node {node} port {port} accepts more than one connection" for ((node, port), n) in source_tracker.items() if n > 1 ]
		if len(errs) > 0:
			raise Exception(errs[-1])

		errs = [ f"edge {i} is not used" for (i, used) in enumerate(consumption) if not used ]
		if len(errs) > 0:
			# TODO: log errs
			raise Exception(errs[-1])

		if not validate_acyclic(config):
			raise Exception("graph is not acyclic")

		if not validate_no_static_deadlock(graph):
			raise Exception("graph has deadlock")

		return graph

	async def run(self):
		runs = [ node.run() for node in self.nodes.values() ]
		await asyncio.gather(*runs)
