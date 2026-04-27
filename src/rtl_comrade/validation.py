from .config import GraphConfig

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
			return True

		state[node] = GREY
		for child in adjacency[node]:
			if not visit(child):
				return False

		state[node] = BLACK
		return True

	return all(visit(node) for node in adjacency)
