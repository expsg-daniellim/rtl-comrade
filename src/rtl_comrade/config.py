"""Serde-backed schema types for graph YAML configuration.

This module defines the typed boundary between user-authored graph YAML and
the harness graph-construction logic.
"""

from dataclasses import dataclass
from inspect import Parameter
from pathlib import Path
from typing import Any, Annotated, Literal

from serde import serde, field, to_dict, Untagged
import typer

from .loader_logger import LoggingConfig

PRIMITIVE_TYPES = { 'int': int, 'float': float, 'str': str, 'bool': bool }

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

@dataclass(slots=True)
class InvalidCLIParameterError(Exception):
	name: str

@serde
@dataclass(slots=True, frozen=True)
class GraphConfigSrcCLI:
	"""A CLI argument or option as the source side of a graph edge or a node config field.

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
		annotation = Annotated[t, typer.Option(help=self.help) if self.option else typer.Argument(help=self.help)]
		try:
			return Parameter(self.cli, Parameter.KEYWORD_ONLY, default=self.default, annotation=annotation)
		except ValueError as e:
			raise InvalidCLIParameterError(self.cli) from e

@serde
@dataclass(slots=True, frozen=True)
class GraphConfigNode:  # pylint: disable=too-many-instance-attributes
	"""One node definition from a graph YAML file.

	Attributes:
		id: The unique runtime id of the node within the graph.
		module: The exported module plugin name to instantiate for this node.
		config: Module-specific configuration passed to the module constructor when supported.
		contract: The exported contract plugin name governing both ends of this node, or ``""`` for the default contract.
		contract_config: Contract-specific configuration passed to the contract constructor when supported.
		input_contract: The exported contract plugin name overriding ``contract`` for input scheduling, or ``""`` to leave the input end to ``contract``.
		input_contract_config: Input-contract-specific configuration passed to the input contract's constructor when supported.
		output_contract: The exported contract plugin name overriding ``contract`` for output processing, or ``""`` to leave the output end to ``contract`` (which processes outputs only if it defines ``process_outputs``).
		output_contract_config: Output-contract-specific configuration passed to the output contract's constructor when supported.
		cli_config: CLI parameter descriptors that supply module config fields at construction time.
		cli_contract_config: CLI parameter descriptors that supply contract config fields at construction time.
		cli_input_contract_config: CLI parameter descriptors that supply input-contract config fields at construction time.
		cli_output_contract_config: CLI parameter descriptors that supply output-contract config fields at construction time.
		contract_port_mappings: Declares the contract-port input surface the node presents to the validator. Keys are the contract-accepted port names (where edges deliver); values are the module ``run(...)`` signature ports each contract port forwards to. ``None`` (the default) means the surface is the module signature itself.
	"""

	id: str
	module: str
	config: dict = field(default_factory=dict)
	contract: str = field(default="")
	contract_config: dict = field(default_factory=dict)
	input_contract: str = field(default="")
	input_contract_config: dict = field(default_factory=dict)
	output_contract: str = field(default="")
	output_contract_config: dict = field(default_factory=dict)
	cli_config: dict[str, GraphConfigSrcCLI] = field(default_factory=dict)
	cli_contract_config: dict[str, GraphConfigSrcCLI] = field(default_factory=dict)
	cli_input_contract_config: dict[str, GraphConfigSrcCLI] = field(default_factory=dict)
	cli_output_contract_config: dict[str, GraphConfigSrcCLI] = field(default_factory=dict)
	contract_port_mappings: dict[str, list[str]]|None = field(default=None)

@serde
@dataclass(slots=True, frozen=True)
class GraphConfigDstPort:
	"""The destination side of a graph edge.

	Attributes:
		node: The id of the downstream destination node.
		port: The destination input port, addressed either by name or by 1-based position.
		required: When ``True``, the default contract awaits a real value on this port even
			if the module input has a default; the input's ``has_default`` is ignored.
	"""

	node: str
	port: int|str = field(default = 1)
	required: bool = field(default = False)

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
		logging: Per-graph custom logging configuration.
	"""

	nodes: list[GraphConfigNode]
	edges: list[GraphConfigEdge]
	modules: list[Path] = field(default_factory=list)
	contracts: list[Path] = field(default_factory=list)
	logging: LoggingConfig = field(default_factory=LoggingConfig)
