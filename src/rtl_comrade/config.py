from serde import serde, field

@serde
class GraphConfigNodePort:
	persistent: bool = field(default=False)

@serde
class GraphConfigNode:
	id: str
	module: str
	config: dict | None
	ports: dict[str|int, GraphConfigNodePort] = field(default_factory=dict)

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
	modules: list[str] = field(default_factory=list)
