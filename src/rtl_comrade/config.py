from serde import serde, field

@serde
class GraphConfigNode:
	id: str
	module: str
	config: dict | None

@serde
class GraphConfigPort:
	node: str
	port: int|str = field(default = 1)

@serde
class GraphConfigEdge:
	src: GraphConfigPort
	dst: GraphConfigPort

@serde
class GraphConfig:
	nodes: list[GraphConfigNode]
	edges: list[GraphConfigEdge]
