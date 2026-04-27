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
class GraphConfigSrcPort:
	node: str
	port: str = field(default = "default")

@serde
class GraphConfigDstPort:
	node: str
	port: int|str = field(default = 1)

@serde
class GraphConfigEdge:
	src: GraphConfigSrcPort
	dst: GraphConfigDstPort

@serde
class GraphConfig:
	nodes: list[GraphConfigNode]
	edges: list[GraphConfigEdge]
	modules: list[str] = field(default_factory=list)
