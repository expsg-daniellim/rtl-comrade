"""Graph assembly and top-level runtime orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
from typing import cast, Any, Callable
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .config_graph import GraphConfig
from .contract_default import DefaultContract
from .loader import load_file_configs
from .logging import HarnessLogger
from .module_cli import ModuleCLI
from .node import Connection, Node
from .validation import validate_no_static_deadlock

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass
class Graph:
	"""A runnable graph composed of instantiated nodes.

	Attributes:
		nodes: Mapping from node id to the instantiated runtime Node.
	"""

	nodes: dict[str, Node]
	cli_nodes: list[Node]
	sig: inspect.Signature

	def __init__(self):
		"""Create an empty graph to be populated during loading.

		Returns:
			None.
		"""

		self.nodes = {}
		self.cli_nodes = []

	@staticmethod
	def from_config(config:GraphConfig) -> Graph:
		"""Construct a runnable graph from an already-parsed GraphConfig.

		Args:
			config: Normalised graph configuration.

		Returns:
			The constructed Graph instance.
		"""

		graph = Graph()

		# Dynamically load plugins
		bind_contextvars(context='harness.load.module')
		module_mappings = load_file_configs(config.modules)
		unbind_contextvars('context')

		bind_contextvars(context='harness.load.contract')
		contract_mappings = load_file_configs(config.contracts)
		unbind_contextvars('context')

		contract_mappings['default'] = DefaultContract

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

		# Initialise the (virtual) cli nodes in the graph
		for (port_name, src) in config.cli_srcs:
			n = Node(id=port_name, Module=ModuleCLI, config={ 'cli': src.cli }, Contract=DefaultContract)
			graph.nodes[n.id] = n
			graph.cli_nodes.append(n)

		graph.sig = config.sig

		# Initialise the edges in the graph
		errors = False
		source_tracker = {} # Verify each dst only has one source
		for node in graph.nodes.values():
			dsts = []
			for edge in config.edges:
				if edge.src.node == node.id:
					# Validate src/dst ports
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

					dsts.append(Connection(edge.src.port, graph.nodes[edge.dst.node], dst_name))  # ty: ignore[invalid-argument-type] — dst_name is narrowed to str by the preceding get_canonical_port check, but ty cannot follow that path

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

	def run(self):  # pragma: no cover
		"""Dummy place holder for the run function. Should never be called.

		Returns:
			None.
		"""

		log.fatal("dummy_run_called", context='harness.graph.cli')

	@staticmethod
	def construct_run(config:GraphConfig, run_cleanup:Callable[[Any], None]):
		"""Build a callable whose signature matches the graph's CLI parameters.

		The returned callable injects the supplied kwargs into the graph's CLI nodes,
		runs the graph, then calls ``run_cleanup``. Its ``__signature__`` is set to
		``self.sig`` so that typer can read the parameter list directly.

		Args:
			run_cleanup: Called after the graph finishes; typically raises ``typer.Exit(1)`` on failure.

		Returns:
			A zero-return callable suitable for registration as a typer subcommand.
		"""

		def run(**kwargs):
			# Only construct actual graph when run
			graph = Graph.from_config(config)
			async def async_run():
				for cli_node in graph.cli_nodes:
					if cli_node.module.cli not in kwargs:
						log.error('missing_option', context='harness.graph.cli', cli=cli_node.module.cli)
					else:
						cli_node.module.value = kwargs[cli_node.module.cli]

				runs = [ node.run() for node in graph.nodes.values() ]
				await asyncio.gather(*runs)

			asyncio.run(async_run())
			run_cleanup()

		run.__signature__ = config.sig # Transform kwargs signature into one readable by Typer
		return run
