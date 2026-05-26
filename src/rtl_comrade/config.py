"""Serde-backed schema types for graph YAML configuration.

This module defines the typed boundary between user-authored graph YAML and
the harness graph-construction logic.
"""

from dataclasses import dataclass
from inspect import Parameter
from typing import Any, Annotated, Literal

from serde import serde, field, to_dict, Untagged
import typer

PRIMITIVE_TYPES = { 'int': int, 'float': float, 'str': str, 'bool': bool }

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
	port: str = field(default = "default")

@dataclass(slots=True, frozen=True)
class InvalidCLIParameterError(Exception):
	name: str

@serde
@dataclass(slots=True, frozen=True)
class GraphConfigSrcCLI:
	"""A CLI argument or option as the source side of a graph edge.

	Attributes:
		cli: The CLI parameter name, used both as the argument/option name and as the virtual node id suffix.
		option: If ``True``, the parameter is a ``--<name>`` option; if ``False``, a positional argument.
		type: The primitive type to coerce the string input to. One of ``"int"``, ``"float"``, ``"bool"``, or ``"str"``.
		default: The default value if the parameter is not supplied. Defaults to ``Parameter.empty``, making the parameter required.
		help: Help text shown in ``--help`` output.
	"""

	cli: str
	option: bool = field(default=True) # if it's not an option it's an argument
	type: Literal["int", "float", "bool", "str"] = field(default="str")
	default: Any = field(default=Parameter.empty) # Might as well instead of None
	help: str|None = field(default=None)

	def as_param(self) -> Parameter:
		"""Build an ``inspect.Parameter`` suitable for inclusion in a typer command signature.

		Returns:
			A keyword-only ``Parameter`` with the appropriate typer annotation.
		"""

		t = PRIMITIVE_TYPES[self.type] if self.type in PRIMITIVE_TYPES else str
		typer_kwargs = { 'help': self.help } # Prevent code duplication
		annotation = Annotated[t, typer.Option(**typer_kwargs) if self.option else typer.Argument(**typer_kwargs)]
		try:
			return Parameter(self.cli, Parameter.KEYWORD_ONLY, default=self.default, annotation=annotation)
		except ValueError as e:
			raise InvalidCLIParameterError(self.cli) from e

@serde
@dataclass(slots=True, frozen=True)
class GraphConfigDstPort:
	"""The destination side of a graph edge.

	Attributes:
		node: The id of the downstream destination node.
		port: The destination input port, addressed either by name or by 1-based position.
	"""

	node: str
	port: int|str = field(default = 1)

@serde(tagging=Untagged)
@dataclass(slots=True, frozen=True)
class GraphConfigEdge:
	"""A directed connection between two node ports.

	Attributes:
		src: The source node-port reference.
		dst: The destination node-port reference.
	"""

	src: GraphConfigSrcPort|GraphConfigSrcCLI
	dst: GraphConfigDstPort

	def __structlog__(self):
		return to_dict(self)

@serde
@dataclass(slots=True, frozen=True)
class GraphFileConfig:
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
