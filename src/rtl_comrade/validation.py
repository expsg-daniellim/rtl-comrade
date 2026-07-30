"""Static graph validation helpers used before runtime execution begins."""

from __future__ import annotations

from collections import deque
from itertools import combinations
from dataclasses import dataclass, field

from .config import GraphConfigSrcPort

from typing import TYPE_CHECKING  # pylint: disable=wrong-import-order
if TYPE_CHECKING:
	from .node import Connection, PreNode
	from .config import GraphConfigNode, GraphConfigEdge


# Solely for the purpose of verifying graph acyclicity - ignores other graph
# invalidities such as dangling edges.
def validate_acyclic(nodes:list[GraphConfigNode], edges:list[GraphConfigEdge]) -> list[str|None]:
	"""Check whether the configured graph contains a cycle.

	Args:
		nodes: List of nodes in the graph to evaluate
		edges: List of edges in the graph to evaluate

	Returns:
		A list of node names participating in detected cycles, or ``None`` entries
		for traversal roots that did not reveal cyclicity.
	"""

	# DFS-colours algorithm
	adjacency:dict[str, list[str]] = { node.id: [] for node in nodes }

	for edge in edges:
		if isinstance(edge.src, GraphConfigSrcPort) and edge.src.node in adjacency and edge.dst.node in adjacency:
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

def validate_no_static_deadlock(prenodes:dict[str, PreNode], node_dsts:dict[str, list[Connection]]) -> StaticDeadlockValidationResults:
	"""Perform conservative first-run deadlock screening over the wired-but-unbuilt graph.

	Args:
		prenodes: Constructed PreNodes keyed by node id, carrying port metadata.
		node_dsts: Outgoing connections keyed by source node id.

	Returns:
		Structured results describing detected deadlock-prone conditions.
	"""

	# Build incoming-port and adjacency maps once.
	incoming:dict[str, set[str]] = {node_id: set() for node_id in prenodes}
	adjacency:dict[str, list[str]] = {node_id: [] for node_id in prenodes}

	for src_id, conns in node_dsts.items():
		for conn in conns:
			incoming[conn.other_node].add(conn.other_port)
			adjacency[src_id].append(conn.other_node)

	res = StaticDeadlockValidationResults()

	# 1. Every first-run-required input must have an incoming edge.
	# Persistent without default is required on first run; default-bearing ports are satisfiable locally, including persistent + default.
	# A config-required port always blocks, so it counts as first-run-required even when it has a default.
	for node_id, pre in prenodes.items():
		for port_name, port in pre.ports.items():
			if (not port.has_default or port_name in pre.required_ports) and port_name not in incoming[node_id]:
				res.edgeless_inputs.append(node_id)

	# 2. At least one node must be source-capable.
	# A source-capable node has no first-run-required inputs; a config-required port is not satisfiable locally.
	sources = { node_id for node_id, pre in prenodes.items() if all(port.has_default and port_name not in pre.required_ports for port_name, port in pre.ports.items()) }
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

	res.non_reachable_nodes = [ node_id for node_id in prenodes if node_id not in seen ]

	return res

def validate_branching(prenodes:dict[str, PreNode], node_dsts:dict[str, list[Connection]]) -> tuple[dict[str, dict[str, frozenset]], list[tuple[str, str]]]:
	"""Propagate control-dependence labels and detect overloaded multi-source ports.

	Walks nodes in topological order, computing each input port's branch label (the intersection of its incoming edge labels) and checking that multi-source ports are fed only by mutually exclusive arms of a common branch origin.

	Args:
		prenodes: Constructed PreNodes keyed by node id, carrying port and structure metadata.
		node_dsts: Outgoing connections keyed by source node id.

	Returns:
		A ``(input_labels, overloaded)`` pair: ``input_labels`` maps each node id to a dict of port name to control-dependence label frozenset; ``overloaded`` lists ``(node_id, port_name)`` pairs whose sources are not mutually exclusive.
	"""

	input_labels:dict[str, dict[str, frozenset]] = { nid: {} for nid in prenodes }
	edge_labels:dict[str, dict[str, list[frozenset]]] = { nid: {} for nid in prenodes }
	declared_arms:dict[str, bool] = {}
	overloaded:list[tuple[str, str]] = []
	indegree = { nid: 0 for nid in prenodes }
	for conns in node_dsts.values():
		for conn in conns:
			indegree[conn.other_node] += 1

	# Perform branch verification
	queue = deque(nid for nid in prenodes if indegree[nid] == 0)
	while len(queue) > 0:
		pre = prenodes[queue.popleft()]

		# Indegree only reaches zero once every incoming edge has been walked, so each port's edge labels are complete by the time they are reached.
		# Collected overloaded nodes (have ports with multiple srcs from non-exclusive branches)
		for name, labels in edge_labels[pre.id].items():
			input_labels[pre.id][name] = frozenset.intersection(*labels)

			# A port is overloaded unless every pair of its srcs is on mutually exclusive arms of a common origin
			if len(labels) > 1 and not all(any(a_origin == b_origin and a_arm != b_arm and prenodes[a_origin].structure.exclusive_arms(a_arm, b_arm, declared_arms[a_origin]) for (a_origin, a_arm) in a for (b_origin, b_arm) in b) for (a, b) in combinations(labels, 2)):
				overloaded.append((pre.id, name))

		inherited:frozenset = frozenset()
		for name, port in pre.ports.items():
			# A gating input is one the node cannot produce its first output without, so its label flows on.
			if not (port.has_default and name not in pre.required_ports):
				inherited |= input_labels[pre.id].get(name, frozenset())

		full_outputs = set(pre.structure.emits) if pre.structure.definite_emits else { conn.self_port for conn in node_dsts[pre.id] }
		arm_map, declared_arms[pre.id] = pre.structure.resolve_arms(full_outputs, getattr(pre.module, 'output_groups', None))

		for conn in node_dsts[pre.id]:
			arm = arm_map.get(conn.self_port)
			edge_labels[conn.other_node].setdefault(conn.other_port, []).append(inherited if arm is None else inherited | { (pre.id, arm) })
			indegree[conn.other_node] -= 1
			if indegree[conn.other_node] == 0:
				queue.append(conn.other_node)

	return input_labels, overloaded
