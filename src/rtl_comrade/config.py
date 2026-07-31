"""Serde-backed schema types for graph YAML configuration.

This module defines the typed boundary between user-authored graph YAML and
the harness graph-construction logic.
"""

import builtins
import importlib
from dataclasses import dataclass
from inspect import Parameter
from pathlib import Path
from typing import Any, Annotated, Self

from serde import serde, field, from_dict, to_dict, Untagged
import typer
from typer.main import get_click_type

from .loader_logger import LoggingConfig
from .logging import LogEvent


def resolve_cli_type(name:str) -> type:
	"""Resolve a CLI type name to its Python type.

	Returns:
		The resolved type.
	"""

	t = getattr(builtins, name, None)
	if isinstance(t, type):
		return t

	if '.' in name:
		mod, _, attr = name.rpartition('.')
		t = getattr(importlib.import_module(mod), attr, None)
		if isinstance(t, type):
			return t

	raise InvalidCLIParameterError(name)

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
		type: The annotation type for the CLI parameter. Builtins (``"int"``, ``"str"``, etc.) by name; non-builtins by qualified name (``"pathlib.Path"``). Validated against ``typer.main.get_click_type``.
		default: The default value if the parameter is not supplied. Defaults to ``Parameter.empty``, making the parameter required.
		help: Help text shown in ``--help`` output.
	"""

	cli: str
	option: bool = field(default=True) # if it's not an option it's an argument
	type: str = field(default="str")
	default: Any = field(default=Parameter.empty) # Might as well instead of None
	help: str|None = field(default=None)

	def as_param(self) -> Parameter:
		"""Build an ``inspect.Parameter`` suitable for inclusion in a typer command signature.

		Returns:
			A keyword-only ``Parameter`` with the appropriate typer annotation.
		"""

		t = resolve_cli_type(self.type)
		info = typer.Option(help=self.help) if self.option else typer.Argument(help=self.help)
		try:
			get_click_type(annotation=t, parameter_info=info)
		except RuntimeError as e:
			raise InvalidCLIParameterError(self.cli) from e

		annotation = Annotated[t, info]
		try:
			return Parameter(self.cli, Parameter.KEYWORD_ONLY, default=self.default, annotation=annotation)
		except ValueError as e:
			raise InvalidCLIParameterError(self.cli) from e

@serde
@dataclass(slots=True)
class GraphConfigNodePlugin:
	"""A unified plugin reference carrying the plugin name, its static config, and any CLI-sourced config fields.

	Used for both module and contract fields on ``GraphConfigNode``. In graph YAML a plugin can be written as a bare string (just the name) or as a mapping with ``name``, ``config``, and ``cli`` keys; the ``try_deserialise`` classmethod handles both forms.

	Attributes:
		name: The exported plugin name, or ``""`` when unset (the default contract).
		config: Static configuration passed to the plugin constructor.
		cli: CLI parameter descriptors that supply config fields at graph-invocation time, keyed by the config field name they populate.
	"""

	name:str = field(default='')
	config:dict = field(default_factory=dict)
	cli: dict[str, GraphConfigSrcCLI] = field(default_factory=dict)

	def is_default(self) -> bool:
		"""Return ``True`` when every field is at its zero value (no plugin configured)."""

		return self.name == '' and len(self.config) == 0 and len(self.cli) == 0

	def validate_cli_config(self, clis:dict[str, GraphConfigSrcCLI], params:list[Parameter]) -> list[LogEvent]:
		"""Validate this plugin's CLI-sourced config and register its parameters on the graph's CLI signature.

		A single CLI parameter may legitimately be declared by several plugins, as long as every declaration agrees.

		Args:
			clis: CLI parameters already registered for this graph, keyed by CLI name. Extended in place.
			params: Signature parameters accumulated for the graph's typer command. Appended to in place.

		Returns:
			Log events for any errors or warnings encountered during validation.
		"""
		errors = []
		for (name, param) in self.cli.items():
			if param.cli == '':
				errors.append(LogEvent('error', 'blank_cli', { 'field': name }))
				continue

			if param.cli in clis:
				if param != clis[param.cli]:
					errors.append(LogEvent('error', 'cli_def_mismatch', { 'cli': param.cli }))
					continue
			else:
				clis[param.cli] = param
				params.append(param.as_param())

			if name in self.config:
				errors.append(LogEvent('warn', 'cli_config_override', { 'field': name }))

		return errors

	def populate_config_with_cli(self, cli_kwargs:dict[str, Any]):
		"""Inject CLI-supplied values into ``config``, overwriting any static defaults.

		Args:
			cli_kwargs: The resolved CLI keyword arguments from the graph's typer command invocation.
		"""

		for name, param in self.cli.items():
			if param.cli in cli_kwargs:
				self.config[name] = cli_kwargs[param.cli]

	@classmethod
	def try_deserialise(cls, val:Any) -> Self|Any:
		"""Coerce a bare string or raw dict into a ``GraphConfigNodePlugin``, used as a pyserde field deserialiser.

		Args:
			val: The raw value from deserialisation — a ``str`` (plugin name shorthand), a ``dict`` (full mapping), or an already-constructed instance.

		Returns:
			A ``GraphConfigNodePlugin`` for string and dict inputs; ``val`` unchanged otherwise.
		"""

		return cls(name=val) if isinstance(val, str) else from_dict(cls, val) if isinstance(val, dict) else val

@serde
@dataclass(slots=True, frozen=True)
class GraphConfigNode:
	"""One node definition from a graph YAML file.

	Attributes:
		id: The unique runtime id of the node within the graph.
		module: The module plugin reference (name, static config, and CLI-sourced config fields).
		contract: The general contract plugin reference governing both ends of this node.
		input_contract: Contract plugin reference overriding ``contract`` for input scheduling only.
		output_contract: Contract plugin reference overriding ``contract`` for output processing only.
		contract_port_mappings: Declares the contract-port input surface the node presents to the validator. Keys are the contract-accepted port names (where edges deliver); values are the module ``run(...)`` signature ports each contract port forwards to. ``None`` (the default) means the surface is the module signature itself.
	"""

	id: str
	module:GraphConfigNodePlugin = field(default_factory=GraphConfigNodePlugin, deserializer=GraphConfigNodePlugin.try_deserialise)
	contract:GraphConfigNodePlugin = field(default_factory=GraphConfigNodePlugin, deserializer=GraphConfigNodePlugin.try_deserialise)
	input_contract:GraphConfigNodePlugin = field(default_factory=GraphConfigNodePlugin, deserializer=GraphConfigNodePlugin.try_deserialise)
	output_contract:GraphConfigNodePlugin = field(default_factory=GraphConfigNodePlugin, deserializer=GraphConfigNodePlugin.try_deserialise)
	contract_port_mappings: dict[str, list[str]]|None = field(default=None)

	def populate_configs_with_cli(self, cli_kwargs:dict[str, Any]):
		"""Propagate CLI-supplied values into every plugin's config on this node.

		Args:
			cli_kwargs: The resolved CLI keyword arguments from the graph's typer command invocation.
		"""

		self.module.populate_config_with_cli(cli_kwargs)
		self.contract.populate_config_with_cli(cli_kwargs)
		self.input_contract.populate_config_with_cli(cli_kwargs)
		self.output_contract.populate_config_with_cli(cli_kwargs)

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
