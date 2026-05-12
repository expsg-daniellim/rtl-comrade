"""Graph assembly and top-level runtime orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .config import GraphConfig
from .contract_default import DefaultContract
from .loader import load_paths, load_config_file
from .node import Connection, Node
from .validation import validate_acyclic, validate_no_static_deadlock

log = structlog.get_logger()

@dataclass(slots=True)
class Graph:
	"""A runnable graph composed of instantiated nodes.

	Attributes:
		nodes: Mapping from node id to the instantiated runtime Node.
	"""

	nodes: dict[str, Node]

	def __init__(self):
		"""Create an empty graph to be populated during loading.

		Returns:
			None.
		"""

		self.nodes = {}

	@staticmethod
	def from_file(path:str) -> Graph:
		"""Load a graph YAML file and construct a runnable Graph.

		Args:
			path: Filesystem path to the graph YAML file.

		Returns:
			The constructed Graph instance.
		"""

		bind_contextvars(context='harness.config', file=path)

		try:
			config = load_config_file(GraphConfig, Path(path))
		finally:
			unbind_contextvars('context', 'file')

		return Graph.from_config(config)

	@staticmethod
	def from_config(config:GraphConfig) -> Graph:
		"""Construct a runnable graph from an already-parsed GraphConfig.

		Args:
			config: Parsed top-level graph configuration.

		Returns:
			The constructed Graph instance.
		"""

		graph = Graph()

		# Dynamically load plugins
		bind_contextvars(context='harness.load.module')
		try:
			module_mappings = load_paths([ Path(path) for path in config.modules ])
		finally:
			unbind_contextvars('context')

		bind_contextvars(context='harness.load.contract')
		try:
			contract_mappings = load_paths([ Path(path) for path in config.contracts ])
		finally:
			unbind_contextvars('context')

		# Validate modules have run functions
		missing_runs = [ name for (name, mod) in module_mappings.items() if not hasattr(mod, 'run') ]
		if len(missing_runs) > 0:
			log.fatal("missing_functions", context='harness.load.module', plugins=missing_runs)

		# Validate contracts have get_inputs functions
		missing_get_inputs = [ name for (name, contract) in contract_mappings.items() if not hasattr(contract, 'get_inputs') ]
		if len(missing_get_inputs) > 0:
			log.fatal("missing_functions", context='harness.load.contract', plugins=missing_get_inputs)

		# Initialise the nodes in the graph
		errors = False
		for i, node in enumerate(config.nodes):
			if node.id in graph.nodes:
				log.error('duplicate_node', context='harness.graph.node', index=i, id=node.id)
				errors = True
			else:
				has_error = False
				if node.module not in module_mappings:
					log.error('invalid_module', context='harness.graph.node', index=i, id=node.id, mod=node.module)
					has_error = True

				if node.contract != '' and node.contract not in contract_mappings:
					log.error('invalid_contract', context='harness.graph.node', index=i, id=node.id, contract=node.contract)
					has_error = True

				if not has_error:
					contract = contract_mappings[node.contract] if node.contract != '' else DefaultContract
					graph.nodes[node.id] = Node(id=node.id, Module=module_mappings[node.module], config=node.config, Contract=contract, contract_config=node.contract_config)
				else:
					errors = True

		if errors:
			log.fatal('invalid_nodes', context='harness.graph.validation')

		# Initialise the edges in the graph
		errors = False
		source_tracker = {} # Verify each dst only has one source
		consumption = [ False for _ in config.edges ] # Keep track of edge usage
		for node in graph.nodes.values():
			dsts = []
			for (i, edge) in enumerate(config.edges):
				if edge.src.node == node.id:
					if edge.dst.node not in graph.nodes:
						log.error('invalid_dst', context='harness.graph.edge', edge=edge)
						consumption[i] = True
						errors = True
						continue

					# Validate src/dst ports
					consumption[i] = True
					has_error = False
					dst_name = graph.nodes[edge.dst.node].get_canonical_port(edge.dst.port)
					if dst_name is None:
						has_error = True
						log.error('invalid_dst_port', context='harness.graph.edge', edge=edge)

					if edge.src.port not in node.structure.emits and node.structure.definite_emits:
						has_error = True
						log.error('invalid_src_port', context='harness.graph.edge', edge=edge)

					if has_error:
						errors = True
						continue

					if not node.structure.definite_emits:
						log.warn('non_definite_emits', context='harness.graph.node', node=node.id, module=type(node.module).__name__)

					dsts.append(Connection(edge.src.port, graph.nodes[edge.dst.node], dst_name))	# ty: ignore[invalid-argument-type] ty cannot determine the None case cannot reach here)

					# Source tracking
					key = (edge.dst.node, dst_name)
					if key not in source_tracker:
						source_tracker[key] = 1
					else:
						source_tracker[key] += 1

			dsts.sort(key=lambda conn: conn.self_port)
			node.set_dsts(dsts)

		if errors:
			log.fatal('invalid_edges', context='harness.graph.validation')

		# Validate each src only accepts one connection
		node_ports = [ (node, port) for ((node, port), n) in source_tracker.items() if n > 1 ]
		if len(node_ports) > 0:
			log.fatal('overloaded_srcs', context='harness.graph.validation', node_ports=node_ports)

		# Validate all edges are consumed (non-fatal)
		unused_edges = [ config.edges[i] for (i, used) in enumerate(consumption) if not used ]
		if len(unused_edges) > 0:
			log.warn('unused_edges', context='harness.graph.validation', edges=unused_edges)

		# Validate the graph is acyclic
		cyclic_nodes = [ name for name in validate_acyclic(config) if name is not None ]
		if len(cyclic_nodes) > 0:
			log.fatal('not_acyclic', context='harness.graph.validation', cyclic_nodes=cyclic_nodes)

		# Static validation of the graph edges
		static_validation_res = validate_no_static_deadlock(graph)
		# 1. Every first-run-required input must have an incoming edge.
		if len(static_validation_res.edgeless_inputs) > 0:
			log.error('edgeless_inputs', context='harness.graph.validation', nodes=static_validation_res.edgeless_inputs)
		# 2. At least one node must be source-capable.
		if not static_validation_res.has_source_capable:
			log.error('no_source', context='harness.graph.validation')
		# 3. Every node must be reachable from some source-capable node.
		if len(static_validation_res.non_reachable_nodes) > 0:
			log.error('non_reachable_nodes', context='harness.graph.validation', nodes=static_validation_res.non_reachable_nodes)

		if static_validation_res.has_error():
			log.fatal('has_deadlock', context='harness.graph.validation')

		return graph

	async def run(self):
		"""Run every node in the graph concurrently until completion.

		Returns:
			None.
		"""

		runs = [ node.run() for node in self.nodes.values() ]
		await asyncio.gather(*runs)
