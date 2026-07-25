"""Normalised graph configuration produced from GraphFileConfig.

This module defines the intermediate type that sits between the serde-backed
YAML schema (config.py) and the runtime graph constructor (graph.py).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from inspect import Signature, Parameter
from pathlib import Path
from typing import cast, Any, Self

import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .config import GraphConfigEdge, GraphConfigNode, GraphConfigSrcCLI, GraphConfigSrcPort, GraphFileConfig
from .config import InvalidCLIParameterError
from .loader_utils import load_config_file
from .loader_logger import LoggingConfig
from .loader_plugin import load_plugin_configs, PluginFileConfig
from .logging import HarnessLogger
from .validation import validate_acyclic

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass(slots=True, frozen=True)
class GraphConfig:  # pylint: disable=too-many-instance-attributes
	"""Normalised graph config with all edges resolved to SrcPort sources.

	Attributes:
		nodes: User-defined node entries (no synthetic CLI nodes).
		edges: All edges with GraphConfigSrcPort sources.
		modules: Plugin paths used to discover module classes.
		contracts: Plugin paths used to discover contract classes.
		cli_sources: Original CLI edge sources in declaration order, used to
			create synthetic CLI nodes and build the graph's CLI signature.
		logging: Per-graph custom logging configuration.
	"""

	nodes: list[GraphConfigNode]
	edges: list[GraphConfigEdge]
	modules: list[PluginFileConfig] = field(default_factory=list)
	contracts: list[PluginFileConfig] = field(default_factory=list)
	cli_srcs: list[tuple[str, GraphConfigSrcCLI]] = field(default_factory=list)
	sig: Signature = field(default_factory=Signature)
	relative_path: Path = field(default_factory=Path)
	logging: LoggingConfig = field(default_factory=LoggingConfig)

	@classmethod
	def from_file(cls, path:Path) -> Self:
		"""Load a graph YAML file and construct a GraphConfig.

		Args:
			path: Filesystem path to the graph YAML file.

		Returns:
			The constructed GraphConfig instance.
		"""

		bind_contextvars(context='harness.config', file=str(path))
		config = load_config_file(GraphFileConfig, path)
		unbind_contextvars('context', 'file')

		try:
			return cls.from_file_config(config, path.parent)
		except InvalidCLIParameterError as e:
			log.fatal('cli_invalid_parameter_name', context='harness.graph.validation_config', name=e.name)
			return None  # pragma: no cover

	@staticmethod
	def validate_cli_config(clis:dict[str, GraphConfigSrcCLI], params:list[Parameter], cli_config:dict[str, GraphConfigSrcCLI], config:dict[str, Any]) -> bool:
		"""Validate one node's CLI-sourced config block and register its parameters on the graph's CLI signature.

		Called once per config block a node can carry — ``config``, ``contract_config``, ``input_contract_config`` and
		``output_contract_config`` — so a single CLI parameter may legitimately be declared by several blocks, as long as
		every declaration agrees. Callers bind the node and block identity into the log context beforehand.

		Args:
			clis: CLI parameters already registered for this graph, keyed by CLI name. Extended in place.
			params: Signature parameters accumulated for the graph's typer command. Appended to in place.
			cli_config: The block's CLI parameter descriptors, keyed by the config field each one supplies.
			config: The corresponding literal config block, checked so a field CLI-supplied and literally set is warned about.

		Returns:
			``True`` if any error was logged for this block, otherwise ``False``.
		"""

		errors = False
		for (name, param) in cli_config.items():
			if param.cli == '':
				log.error('blank_cli', context='harness.graph_config.validation', field=name)
				errors = True
				continue

			if param.cli in clis:
				if param != clis[param.cli]:
					log.error('cli_def_mismatch', context='harness.graph_config.validation', cli=param.cli)
					errors = True
					continue
			else:
				clis[param.cli] = param
				params.append(param.as_param())

			if name in config:
				log.warn('cli_config_override', context='harness.graph_config.validation', field=name)

		return errors

	@classmethod
	def from_file_config(cls, config:GraphFileConfig, relative_path:Path=Path()) -> Self:
		"""Expand CLI edges into SrcPort replacements and collect cli_sources.

		Returns:
			None.
		"""

		# Validate duplicate nodes
		errors = False
		nodes = set({})
		for (i, node) in enumerate(config.nodes):
			if node.id in nodes:
				errors = True
				log.error('duplicate_node', context='harness.graph_config', index=i, id=node.id)
			else:
				nodes.add(node.id)

		if errors:
			log.fatal('invalid_nodes', context='harness.graph_config.validation')

		# Process CLI edges
		edges = [ edge for edge in config.edges if isinstance(edge.src, GraphConfigSrcPort) ]

		errors = False
		clis = {}
		cli_srcs = []
		params = []
		for (i, edge) in enumerate(config.edges):
			if isinstance(edge.src, GraphConfigSrcCLI):
				# Validate CLI params
				if edge.src.cli == '':
					log.error('blank_cli', context='harness.graph_config.validation', index=i)
					errors = True
					continue

				port_name = f'cli-{edge.src.cli}'
				if port_name in nodes:
					log.error('duplicate_node', context='harness.graph_config.validation', id=port_name, index=i)
					errors = True
					continue

				if edge.src.cli in clis:
					if edge.src != clis[edge.src.cli]:
						log.error('cli_def_mismatch', context='harness.graph_config.validation', id=port_name, index=i)
						errors = True
						continue
				else:
					clis[edge.src.cli] = edge.src
					params.append(edge.src.as_param())

				cli_srcs.append((port_name, edge.src))
				edges.append(GraphConfigEdge(GraphConfigSrcPort(port_name), edge.dst))

		if errors:
			log.fatal('invalid_cli_edges', context='harness.graph_config.validation')

		# Process node config CLI params
		for (i, node) in enumerate(config.nodes):
			bind_contextvars(index=i, node=node.id)
			bind_contextvars(config_type='config')
			node_errors = cls.validate_cli_config(clis, params, node.cli_config, node.config)

			bind_contextvars(config_type='contract_config')
			contract_errors = cls.validate_cli_config(clis, params, node.cli_contract_config, node.contract_config)

			bind_contextvars(config_type='input_contract_config')
			input_contract_errors = cls.validate_cli_config(clis, params, node.cli_input_contract_config, node.input_contract_config)

			bind_contextvars(config_type='output_contract_config')
			output_contract_errors = cls.validate_cli_config(clis, params, node.cli_output_contract_config, node.output_contract_config)

			unbind_contextvars('index', 'node', 'config_type')
			errors |= node_errors or contract_errors or input_contract_errors or output_contract_errors

		if errors:
			log.fatal('invalid_cli_config', context='harness.graph_config.validation')

		# Validate edges
		all_node_ids = nodes | {port_name for port_name, _ in cli_srcs}
		unused_edges = [ edge for edge in edges if edge.src.node not in all_node_ids ] # ty: ignore[unresolved-attribute] — edges is filtered to GraphConfigSrcPort sources at the top of this function
		if unused_edges:
			log.warn('unused_edges', context='harness.graph_config.validation', edges=unused_edges)

		invalid_dst_edges = [ edge for edge in edges if edge.dst.node not in all_node_ids ]
		if len(invalid_dst_edges) > 0:
			for edge in invalid_dst_edges:
				log.error('invalid_dst', context='harness.graph_config.validation', edge=edge)
			log.fatal('invalid_edges', context='harness.graph_config.validation')

		cyclic_nodes = [ name for name in validate_acyclic(config.nodes, edges) if name is not None ]
		if cyclic_nodes:
			log.fatal('not_acyclic', context='harness.graph_config.validation', cyclic_nodes=cyclic_nodes)

		return cls(
			nodes = config.nodes,
			edges = edges,
			cli_srcs = cli_srcs,
			modules = load_plugin_configs(config.modules, relative_path),
			contracts = load_plugin_configs(config.contracts, relative_path),
			sig=Signature(params),
			relative_path=relative_path,
			logging=config.logging
		)
