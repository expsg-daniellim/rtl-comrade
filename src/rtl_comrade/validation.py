from .config import GraphConfig

# TODO: better more granular error reporting for each validation function. Type 'ValidationError'; also use in structure.py
# Validators written by ChatGPT because I got lazy

# Solely for the purpose of verifying graph acyclicity - ignores other graph invalidities such as dangling edges
def validate_acyclic(config:GraphConfig) -> bool:
	# DFS-colours algorithm
	adjacency = { node.id: [] for node in config.nodes }

	for edge in config.edges:
		if edge.src.node in adjacency and edge.dst.node in adjacency:
			adjacency[edge.src.node].append(edge.dst.node)

	WHITE, GREY, BLACK = 0, 1, 2
	state = { node: WHITE for node in adjacency }

	def visit(node:str) -> bool:
		if state[node] == GREY:
			return False
		if state[node] == BLACK:
			# TODO: report exact node where cyclicity is detected
			return True

		state[node] = GREY
		for child in adjacency[node]:
			if not visit(child):
				return False

		state[node] = BLACK
		return True

	return all(visit(node) for node in adjacency)

def validate_no_static_deadlock(graph) -> bool:
	# Build incoming-port and adjacency maps once.
	incoming = {node_id: set() for node_id in graph.nodes}
	adjacency = {node_id: [] for node_id in graph.nodes}

	for node_id, node in graph.nodes.items():
		for conn in node.dsts or []:
			incoming[conn.other_node.id].add(conn.other_port)
			adjacency[node_id].append(conn.other_node.id)

	# 1. Every first-run-required input must have an incoming edge.
	# Persistent without default is required on first run; default-bearing ports are satisfiable locally, including persistent + default.
	for node_id, node in graph.nodes.items():
		for port_name, port in node.ports.items():
			if not port.has_default and port_name not in incoming[node_id]:
				return False # TODO: collect list of nodes

	# 2. At least one node must be source-capable.
	# A source-capable node has no first-run-required inputs.
	sources = { node_id for node_id, node in graph.nodes.items() if all(port.has_default for port in node.ports.values()) }
	if not sources:
		return False # TODO: exact error message

	# 3. Every node must be reachable from some source-capable node.
	seen = set()
	stack = list(sources)

	while stack:
		node_id = stack.pop()
		if node_id in seen:
				continue

		seen.add(node_id)
		stack.extend(adjacency[node_id])

	# TODO: return !union set/seen
	return seen == set(graph.nodes)
