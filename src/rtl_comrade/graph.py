"""Graph assembly and top-level runtime orchestration."""

from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from dataclasses import dataclass
import inspect
from itertools import groupby
from typing import cast, Any, Callable, Self
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .config_graph import GraphConfig
from .contract import ContractDefinitions, InvalidContractParameterTypeError, MissingContractError, MissingContractFunctionError, MissingContractParameterError
from .contract_default import DefaultContract
from .loader_plugin import load_plugins
from .logging import HarnessLogger
from .module import GraphModule
from .module_cli import ModuleCLI
from .node import Connection, Node, PreNode
from .port import Port
from .validation import validate_no_static_deadlock

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass(frozen=True, slots=True)
class Graph:
	"""A runnable graph composed of instantiated nodes.

	Attributes:
		nodes: Mapping from node id to the instantiated runtime Node.
		cli_nodes: List of virtual GraphCLI module nodes designed for CLI argument ingress.
		sig: Virtual function signature for use with typer command derivation.
	"""

	nodes: dict[str, Node]
	cli_nodes: list[Node]
	sig: inspect.Signature

	@classmethod
	def from_config(cls, config:GraphConfig, cli_kwargs:dict[str, Any]|None=None) -> Self:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
		"""Construct a runnable graph from an already-parsed GraphConfig.

		Args:
			config: Normalised graph configuration.
			cli_kwargs: Parsed CLI parameter values keyed by CLI name, written into each node's module and contract
				config blocks where a ``cli_*_config`` descriptor claims them. ``None`` is treated as empty.

		Returns:
			The constructed Graph instance.
		"""

		if cli_kwargs is None:
			cli_kwargs = {}

		# Dynamically load plugins
		bind_contextvars(context='harness.load.module')
		module_mappings = { name: GraphModule.from_module(Module) for (name, Module) in load_plugins(config.modules, 'modules').items() }
		unbind_contextvars('context')

		bind_contextvars(context='harness.load.contract')
		contract_mappings = load_plugins(config.contracts, 'contracts')
		unbind_contextvars('context')

		contract_mappings['default'] = DefaultContract

		# Validate modules have run functions
		missing_runs = [ name for (name, mod) in module_mappings.items() if not (hasattr(mod.Module, 'run') and callable(getattr(mod.Module, 'run'))) ]
		if len(missing_runs) > 0:  # pragma: no cover
			log.fatal("missing_functions", context='harness.load.module', plugins=missing_runs)  # pragma: no cover

		# Initialise the initialise set of contractless prenodes
		prenodes:dict[str, PreNode] = {}
		cli_ids:list[str] = []
		errors = False
		for i, node in enumerate(config.nodes):
			if node.module not in module_mappings:
				log.error('invalid_module', context='harness.graph.node', index=i, id=node.id, mod=node.module)
				errors = True
				continue

			# Determine the node's input-port surface and definiteness.
			ports = None
			definite_inputs_override = node.contract_port_mappings is not None
			mod = module_mappings[node.module]
			if node.contract_port_mappings is not None:
				# An invalid target is an indefinite input with no contract_port_mapping which cannot be statically validated
				invalid_targets = [ target for targets in node.contract_port_mappings.values() for target in targets if target not in mod.ports ] if mod.structure.definite_inputs else []
				if len(invalid_targets) > 0:
					log.error('invalid_mapping_target', context='harness.graph.node', index=i, id=node.id, targets=invalid_targets)
					errors = True
					continue

				# An empty target list forwards to nothing, so it cannot inherit a default
				ports = OrderedDict({ cport: Port(cport, has_default=len(targets) > 0 and all(name in mod.ports and mod.ports[name].has_default for name in targets)) for cport, targets in node.contract_port_mappings.items() })
			elif not mod.structure.definite_inputs:
				# A positional port cannot be resolved against a non-definite surface that has no declared port order, so reject it before building the surface.
				positional_ports = [ edge.dst.port for edge in config.edges if edge.dst.node == node.id and not isinstance(edge.dst.port, str) ]
				if len(positional_ports) > 0:
					log.error('non_definite_positional_destination_port', context='harness.graph.node', index=i, id=node.id, ports=positional_ports)
					errors = True
					continue

				# Assemble port mappings from incoming edges for non-definite-input modules.
				ports = OrderedDict({ edge.dst.port: Port(edge.dst.port) for edge in config.edges if edge.dst.node == node.id and isinstance(edge.dst.port, str) })

			# Consolidate contract definitions
			# Check for obsolete contract - contract smothered by input_contract and output_contract on top
			if node.contract != '' and node.input_contract != '' and node.output_contract != '':
				log.warn('obsolete_contract', context='harness.graph.node', index=i, id=node.id)

			try:
				contract_definitions = ContractDefinitions.from_node_config(node, contract_mappings)
			except MissingContractError as e:
				log.error('invalid_contract', context='harness.graph.node', index=i, id=node.id, field=e.field, contract=e.name, available=e.available)
				errors = True
				continue
			except MissingContractFunctionError as e:
				log.error('missing_contract_function', context='harness.graph.node', index=i, id=node.id, field=e.field, contract=e.name, method=e.method, available_functions=e.available_functions)
				errors = True
				continue
			except MissingContractParameterError as e:
				log.error('missing_contract_parameter', context='harness.graph.node', index=i, id=node.id, field=e.field, contract=e.name, function=e.function, parameter=e.parameter)
				errors = True
				continue
			except InvalidContractParameterTypeError as e:
				log.error('invalid_contract_parameter_type', context='harness.graph.node', index=i, id=node.id, field=e.field, contract=e.name, function=e.function, parameter=e.parameter, type_=e.type_)
				errors = True
				continue

			required_ports = [ edge.dst.port for edge in config.edges if edge.dst.node == node.id and edge.dst.required ]

			# Populate configs with CLI args
			for name, param in node.cli_config.items():
				if param.cli in cli_kwargs:
					node.config[name] = cli_kwargs[param.cli]

			for name, param in node.cli_contract_config.items():
				if param.cli in cli_kwargs:
					node.contract_config[name] = cli_kwargs[param.cli]

			for name, param in node.cli_input_contract_config.items():
				if param.cli in cli_kwargs:
					node.input_contract_config[name] = cli_kwargs[param.cli]

			for name, param in node.cli_output_contract_config.items():
				if param.cli in cli_kwargs:
					node.output_contract_config[name] = cli_kwargs[param.cli]

			prenodes[node.id] = PreNode(id=node.id, module=mod, config=node.config, contract_definitions=contract_definitions, relative_path=config.relative_path, ports=ports, required_ports=required_ports, definite_inputs_override=definite_inputs_override)

		if errors:
			log.fatal('invalid_nodes', context='harness.graph.validation')

		# Initialise the (virtual) cli prenodes in the graph
		module_cli = GraphModule.from_module(ModuleCLI)
		for (port_name, src) in config.cli_srcs:
			prenodes[port_name] = PreNode(id=port_name, module=module_cli, config={ 'cli': src.cli }, contract_definitions=ContractDefinitions.default())
			cli_ids.append(port_name)

		# Consolidate and validate graph edges
		errors = False
		source_tracker = {} # Verify each dst only has one source (keyed by (dst id, dst port))
		node_dsts:dict[str, list[Connection]] = { nid: [] for nid in prenodes }
		for pre in prenodes.values():
			for edge in config.edges:
				if edge.src.node == pre.id: # ty: ignore[unresolved-attribute] — config.edges holds only GraphConfigSrcPort sources after from_file_config normalises CLI edges
					# Validate src/dst ports
					has_error = False
					dst_name = prenodes[edge.dst.node].get_canonical_port(edge.dst.port)
					if dst_name is None:
						if prenodes[edge.dst.node].definite_inputs or not isinstance(edge.dst.port, str):
							has_error = True
							log.error('invalid_dst_port', context='harness.graph.edge', edge=edge)
						else:  # pragma: no cover
							dst_name = edge.dst.port  # pragma: no cover

					if edge.src.port not in pre.structure.emits and pre.structure.definite_emits: # ty: ignore[unresolved-attribute] — config.edges holds only GraphConfigSrcPort sources after from_file_config normalises CLI edges
						has_error = True
						log.error('invalid_src_port', context='harness.graph.edge', edge=edge)

					if has_error:
						errors = True
						continue

					if not pre.structure.definite_emits:
						log.warn('non_definite_emits', context='harness.graph.node', node=pre.id, module=type(pre.module).__name__)

					node_dsts[pre.id].append(Connection(edge.src.port, edge.dst.node, dst_name))  # ty: ignore[unresolved-attribute, invalid-argument-type] — dst_name is narrowed to a real port name by the get_canonical_port check; config.edges holds only GraphConfigSrcPort sources

					# Source tracking
					key = (edge.dst.node, dst_name)
					source_tracker[key] = source_tracker.get(key, 0) + 1

			node_dsts[pre.id].sort(key=lambda conn: conn.self_port)

			if not pre.definite_inputs:
				log.warn('non_definite_inputs', context='harness.graph.node', node=pre.id, module=type(pre.module).__name__)

		if errors:
			log.fatal('invalid_edges', context='harness.graph.validation')

		# Validate each src only accepts one connection
		node_ports = [ (node, port) for ((node, port), n) in source_tracker.items() if n > 1 ]
		if len(node_ports) > 0:
			log.fatal('overloaded_srcs', context='harness.graph.validation', node_ports=node_ports)

		# Static validation of the graph edges
		static_validation_res = validate_no_static_deadlock(prenodes, node_dsts)
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

		# Propagate control-dependence labels to each input port (topological over the already-acyclic graph)
		input_labels:dict[str, dict[str, frozenset]] = { nid: {} for nid in prenodes }
		indegree = { nid: 0 for nid in prenodes }
		for conns in node_dsts.values():
			for conn in conns:
				indegree[conn.other_node] += 1

		queue = deque(nid for nid in prenodes if indegree[nid] == 0)
		while len(queue) > 0:
			pre = prenodes[queue.popleft()]

			inherited:frozenset = frozenset()
			for name, port in pre.ports.items():
				# A gating input is one the node cannot produce its first output without, so its label flows on.
				if not (port.has_default and name not in pre.required_ports):
					inherited |= input_labels[pre.id].get(name, frozenset())

			full_outputs = set(pre.structure.emits) if pre.structure.definite_emits else { conn.self_port for conn in node_dsts[pre.id] }
			arm_map = pre.structure.resolve_arms(full_outputs, getattr(pre.module, 'output_groups', None))

			for conn in node_dsts[pre.id]:
				arm = arm_map.get(conn.self_port)
				input_labels[conn.other_node][conn.other_port] = inherited if arm is None else inherited | { (pre.id, arm) }
				indegree[conn.other_node] -= 1
				if indegree[conn.other_node] == 0:
					queue.append(conn.other_node)

		# Construct each node's runtime dispatch map (source output port -> destination Ports) from its id-space connections.
		port_dsts = { nid: { self_port: [ prenodes[conn.other_node].ports[conn.other_port] for conn in conns ] for self_port, conns in groupby(node_dsts[nid], key=lambda conn: conn.self_port) } for nid in prenodes }

		# Build graph nodes from prenodes
		nodes = { nid: Node.from_prenode(pre, port_dsts[nid], input_labels[nid]) for nid, pre in prenodes.items() }
		cli_nodes = [ nodes[cid] for cid in cli_ids ]

		return cls(nodes=nodes, cli_nodes=cli_nodes, sig=config.sig)

	def run(self):  # pragma: no cover
		"""Dummy place holder for the run function. Should never be called.

		Returns:
			None.
		"""

		log.fatal("dummy_run_called", context='harness.graph.cli')

	@classmethod
	def construct_run(cls, config:GraphConfig, setup_logging:Callable[[list[Any], list[Any], bool], None], run_cleanup:Callable[[], None]):
		"""Build a callable whose signature matches the graph's CLI parameters.

		The returned callable injects the supplied kwargs into the graph's CLI nodes,
		runs the graph, then calls ``run_cleanup``. Its ``__signature__`` is set to
		``self.sig`` so that typer can read the parameter list directly.

		Args:
			setup_logging: Constructs and installs the resolved ``(processors, handlers, include_default)`` for the graph run.
			run_cleanup: Called after the graph finishes; typically raises ``typer.Exit(1)`` on failure.

		Returns:
			A zero-return callable suitable for registration as a typer subcommand.
		"""

		def run(**kwargs):
			# Only construct actual graph when run
			graph = cls.from_config(config, kwargs)
			# Custom logging applies to the run only; resolve lazily after construction, before node execution.
			processors, handlers = config.logging.load(config.relative_path)
			setup_logging(processors, handlers, config.logging.include_default)
			async def async_run():
				for cli_node in graph.cli_nodes:
					if cli_node.module.cli not in kwargs:
						log.error('missing_option', context='harness.graph.cli', cli=cli_node.module.cli)
					else:
						cli_node.module.value = kwargs[cli_node.module.cli]

				runs = [ node.run() for node in graph.nodes.values() ]
				await asyncio.gather(*runs)
				run_cleanup()

			asyncio.run(async_run())

		run.__signature__ = config.sig # ty: ignore[unresolved-attribute] — Transform kwargs signature into one readable by Typer
		return run
