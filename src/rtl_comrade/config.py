"""Serde-backed schema types for graph YAML configuration.

This module defines the typed boundary between user-authored graph YAML and
the harness graph-construction logic.
"""

from dataclasses import dataclass
from serde import serde, field, to_dict


@serde
@dataclass(slots=True, frozen=True)
class GraphConfigNode:
	"""One node definition from a graph YAML file.

	Attributes:
		id: The unique runtime id of the node within the graph.
		module: The exported module plugin name to instantiate for this node.
		config: Module-specific configuration passed to the module constructor when supported.
		contract: The exported contract plugin name for this node, or ``""`` for the default contract.
		contract_config: Contract-specific configuration passed to the contract constructor when supported.
	"""

	id: str
	module: str
	config: dict = field(default_factory=dict)
	contract: str = field(default="")
	contract_config: dict = field(default_factory=dict)


@serde
@dataclass(slots=True, frozen=True)
class GraphConfigSrcPort:
	"""The source side of a graph edge.

	Attributes:
		node: The id of the upstream source node.
		port: The emitted source port name, defaulting to ``"default"``.
	"""

	node: str
	port: str = field(default="default")


@serde
@dataclass(slots=True, frozen=True)
class GraphConfigDstPort:
	"""The destination side of a graph edge.

	Attributes:
		node: The id of the downstream destination node.
		port: The destination input port, addressed either by name or by 1-based position.
	"""

	node: str
	port: int | str = field(default=1)


@serde
@dataclass(slots=True, frozen=True)
class GraphConfigEdge:
	"""A directed connection between two node ports.

	Attributes:
		src: The source node-port reference.
		dst: The destination node-port reference.
	"""

	src: GraphConfigSrcPort
	dst: GraphConfigDstPort

	def __structlog__(self):
		return to_dict(self)


@serde
@dataclass(slots=True, frozen=True)
class GraphConfig:
	"""The top-level graph configuration schema loaded from YAML.

	Attributes:
		nodes: The node definitions to instantiate in the runtime graph.
		edges: The directed connections wiring node outputs to node inputs.
		modules: Plugin paths used to discover module classes.
		contracts: Plugin paths used to discover contract classes.
	"""

	nodes: list[GraphConfigNode]
	edges: list[GraphConfigEdge]
	modules: list[str] = field(default_factory=list)
	contracts: list[str] = field(default_factory=list)
