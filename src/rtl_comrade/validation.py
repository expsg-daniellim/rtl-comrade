from dataclasses import dataclass, field

from .config import GraphConfig
from .module import ModuleWrapper

# Validators written by ChatGPT because I got lazy

# Solely for the purpose of verifying graph acyclicity - ignores other graph invalidities such as dangling edges
def validate_acyclic(config:GraphConfig) -> list[str|None]:
	# DFS-colours algorithm
	adjacency = { node.id: [] for node in config.nodes }

	for edge in config.edges:
		if edge.src.node in adjacency and edge.dst.node in adjacency:
			adjacency[edge.src.node].append(edge.dst.node)

	WHITE, GREY, BLACK = 0, 1, 2
	state = { node: WHITE for node in adjacency }

	# Returns name of node where cyclicity is last observed, None otherwise
	def visit(node:str) -> str|None:
		if state[node] == GREY:
			return node
		if state[node] == BLACK:
			return None

		state[node] = GREY
		for child in adjacency[node]:
			if visit(child) is not None:
				return node

		state[node] = BLACK
		return None

	return [visit(node) for node in adjacency]

# Holder class to return validation results
@dataclass
class StaticDeadlockValidationResults:
	edgeless_inputs: list[ModuleWrapper] = field(default_factory=list)
	has_source_capable: bool = True # Condition 2
	non_reachable_nodes: list[ModuleWrapper] = field(default_factory=list)	# Condition 3

	def has_error(self) -> bool:
		return (len(self.edgeless_inputs) > 0) or (not self.has_source_capable) or (len(self.non_reachable_nodes) > 0)

def validate_no_static_deadlock(graph) -> StaticDeadlockValidationResults:
	# Build incoming-port and adjacency maps once.
	incoming = {node_id: set() for node_id in graph.nodes}
	adjacency = {node_id: [] for node_id in graph.nodes}

	for node_id, node in graph.nodes.items():
		for conn in node.dsts or []:
			incoming[conn.other_node.id].add(conn.other_port)
			adjacency[node_id].append(conn.other_node.id)

	res = StaticDeadlockValidationResults()

	# 1. Every first-run-required input must have an incoming edge.
	# Persistent without default is required on first run; default-bearing ports are satisfiable locally, including persistent + default.
	for node_id, node in graph.nodes.items():
		for port_name, port in node.ports.items():
			if not port.has_default and port_name not in incoming[node_id]:
				res.edgeless_inputs.append(node)

	# 2. At least one node must be source-capable.
	# A source-capable node has no first-run-required inputs.
	sources = { node_id for node_id, node in graph.nodes.items() if all(port.has_default for port in node.ports.values()) }
	res.has_source_capable = bool(sources)

	# 3. Every node must be reachable from some source-capable node.
	seen = set()
	stack = list(sources)

	while stack:
		node_id = stack.pop()
		if node_id in seen:
				continue

		seen.add(node_id)
		stack.extend(adjacency[node_id])

	res.non_reachable_ports = [ node for (node_id, node) in graph.nodes.items() if node_id not in seen ]

	return res
