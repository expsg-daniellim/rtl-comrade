from dataclasses import dataclass

from .config import GraphConfig

@dataclass
class Node:
	id: str
	visited: bool
	connected: list[Node]
	has_parent: bool

	# True means a node gets visited twice
	def visit(self) -> bool:
		if self.visited:
			return True

		self.visited = True
		if len(self.connected) <= 0:
			return False
		else:
			for child in self.connected:
				if child.visit() == True:
					return True
			return False

# Solely for the purpose of verifying graph acyclicity - ignores other graph invalidities such as dangling edges
def validate_acyclic(config:GraphConfig) -> bool:
	nodes = { node.id: Node(node.id, 0, [], False) for node in config.nodes }
	for node in nodes.values():
		node.connected = [ nodes[edge.dst.node] for edge in config.edges if edge.src.node == node.id and edge.dst.node in nodes ]
		for child in node.connected:
			child.has_parent = True

	starting_nodes = [ node for node in nodes.values() if not node.has_parent ]
	for starting_node in starting_nodes:
		# Reset graph
		for node in nodes.values():
			node.visited = False
		# DFS
		if starting_node.visit():
			return False

	return True
