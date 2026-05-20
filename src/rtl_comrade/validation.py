"""Static graph validation helpers used before runtime execution begins."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import GraphConfig

from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from .graph import Graph


# Solely for the purpose of verifying graph acyclicity - ignores other graph
# invalidities such as dangling edges.
def validate_acyclic(config:GraphConfig) -> list[str|None]:
	"""Check whether the configured graph contains a cycle.

	Args:
		config: Parsed graph configuration to validate.

		Returns:
			A list of node names participating in detected cycles, or ``None`` entries
			for traversal roots that did not reveal cyclicity.
	"""

	# DFS-colours algorithm
	adjacency:dict[str, list[str]] = { node.id: [] for node in config.nodes }

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

@dataclass(slots=True)
class StaticDeadlockValidationResults:
	"""Results from the conservative static deadlock screening pass.

	Attributes:
		edgeless_inputs: Nodes with first-run-required inputs lacking incoming edges.
		has_source_capable: Whether at least one node can run without upstream input.
		non_reachable_nodes: Nodes unreachable from any source-capable node.
	"""

	edgeless_inputs: list[str] = field(default_factory=list)
	has_source_capable: bool = True # Condition 2
	non_reachable_nodes: list[str] = field(default_factory=list)	# Condition 3

	def has_error(self) -> bool:
		"""Return whether any static deadlock condition was detected.

		Returns:
			``True`` if any deadlock-prone condition was found, otherwise ``False``.
		"""

		return (len(self.edgeless_inputs) > 0) or (not self.has_source_capable) or (len(self.non_reachable_nodes) > 0)

def validate_no_static_deadlock(graph:Graph) -> StaticDeadlockValidationResults:
	"""Perform conservative first-run deadlock screening on a constructed graph.

	Args:
		graph: Constructed runtime graph with nodes and validated edges.

		Returns:
			Structured results describing detected deadlock-prone conditions.
	"""

	# Build incoming-port and adjacency maps once.
	incoming:dict[str, set[str]] = {node_id: set() for node_id in graph.nodes}
	adjacency:dict[str, list[str]] = {node_id: [] for node_id in graph.nodes}

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
				res.edgeless_inputs.append(node_id)

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

	res.non_reachable_nodes = [ node_id for node_id in graph.nodes if node_id not in seen ]

	return res
