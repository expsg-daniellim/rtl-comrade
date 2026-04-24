from .config import GraphConfig
from dataclasses import dataclass
from serde.yaml import from_yaml

@dataclass
class Connection:
	self_port: int
	other_node: str
	other_port: int

@dataclass
class Node:
	module: str
	config: dict | None
	srcs: list[Connection]
	dsts: list[Connection]

@dataclass
class Graph:
	nodes: dict[str, Node]

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
		# TODO: expand implicit ports in edges

		for i, node in enumerate(config.nodes):
			if node.id in graph.nodes:
				errs.append(f"Node entry {i + 1} is a duplicate id")
			else:
				srcs = list(map(lambda edge: Connection(edge.dst.port, edge.src.node, edge.src.port), filter(lambda edge: edge.dst.node == node.id, config.edges)))
				dsts = list(map(lambda edge: Connection(edge.src.port, edge.dst.node, edge.dst.port), filter(lambda edge: edge.src.node == node.id, config.edges)))
				graph.nodes[node.id] = Node(node.module, node.config, srcs, dsts)
		
		# TODO: Verify that all edges are used
		#consumption = [(False, False) for _ in config.edges]
		#for i, edges in enumerate(config.edges):
	
		if len(errs) > 0:
			raise errs

		return graph
