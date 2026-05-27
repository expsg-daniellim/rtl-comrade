"""Normalised graph configuration produced from GraphFileConfig.

This module defines the intermediate type that sits between the serde-backed
YAML schema (config.py) and the runtime graph constructor (graph.py).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from inspect import Signature
from pathlib import Path
from typing import cast

import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .config import GraphConfigEdge, GraphConfigNode, GraphConfigSrcCLI, GraphConfigSrcPort, GraphFileConfig
from .config import InvalidCLIParameterError
from .loader import load_config_file, load_plugin_configs, PluginFileConfig
from .logging import HarnessLogger
from .validation import validate_acyclic

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass(slots=True, frozen=True)
class GraphConfig:
	"""Normalised graph config with all edges resolved to SrcPort sources.

	Attributes:
		nodes: User-defined node entries (no synthetic CLI nodes).
		edges: All edges with GraphConfigSrcPort sources.
		modules: Plugin paths used to discover module classes.
		contracts: Plugin paths used to discover contract classes.
		cli_sources: Original CLI edge sources in declaration order, used to
			create synthetic CLI nodes and build the graph's CLI signature.
	"""

	nodes: list[GraphConfigNode]
	edges: list[GraphConfigEdge]
	modules: list[PluginFileConfig] = field(default_factory=list)
	contracts: list[PluginFileConfig] = field(default_factory=list)
	cli_srcs: list[tuple[str, GraphConfigSrcCLI]] = field(default_factory=list)
	sig: Signature = field(default_factory=Signature)
	relative_path: Path = field(default_factory=Path)

	@staticmethod
	def from_file(path:str) -> GraphConfig:
		"""Load a graph YAML file and construct a GraphConfig.

		Args:
			path: Filesystem path to the graph YAML file.

		Returns:
			The constructed GraphConfig instance.
		"""

		bind_contextvars(context='harness.config', file=path)
		config = load_config_file(GraphFileConfig, Path(path))
		unbind_contextvars('context', 'file')

		try:
			return GraphConfig.from_file_config(config, Path(path).parent)
		except InvalidCLIParameterError as e:
			log.fatal('cli_invalid_parameter_name', context='harness.graph.validation_config', name=e.name)
			return None  # pragma: no cover

	@staticmethod
	def from_file_config(config:GraphFileConfig, relative_path:Path=Path()) -> GraphConfig:
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
		clis = set({})
		cli_srcs = []
		params = []
		for (i, edge) in enumerate(config.edges):
			if isinstance(edge.src, GraphConfigSrcCLI):
				# Validate CLI params
				if edge.src.cli == '':
					log.error('blank_cli', context='harness.graph_config.validation', index=i)
					errors = True
					continue

				if edge.src.cli in clis:
					log.error('duplicate_cli', context='harness.graph_config.validation', index=i, cli=edge.src.cli)
					errors = True
					continue

				port_name = f'cli-{edge.src.cli}'
				if port_name in nodes:
					log.error('duplicate_node', context='harness.graph_config.validation', id=port_name, index=None)
					errors = True
					continue

				clis.add(edge.src.cli)
				cli_srcs.append((port_name, edge.src))
				edges.append(GraphConfigEdge(GraphConfigSrcPort(port_name), edge.dst))
				params.append(edge.src.as_param())

		if errors:
			log.fatal('invalid_cli_edges', context='harness.graph_config.validation')

		# Validate edges
		all_node_ids = nodes | {port_name for port_name, _ in cli_srcs}
		unused_edges = [ edge for edge in edges if edge.src.node not in all_node_ids ]
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

		return GraphConfig(
			nodes = config.nodes,
			edges = edges,
			cli_srcs = cli_srcs,
			modules = load_plugin_configs(config.modules, relative_path),
			contracts = load_plugin_configs(config.contracts, relative_path),
			sig=Signature(params),
			relative_path=relative_path
		)
