from __future__ import annotations

from .config import GraphConfig
from dataclasses import dataclass
from pathlib import Path
from serde.yaml import from_yaml
import asyncio
import structlog

from .contract_default import DefaultContract
from .loader import load_paths, load_config_file
from .loader import LoadFileNotFoundError, LoadInvalidSpecError, LoadMalformedSpecError, LoadSpecNoLoaderError, LoadModuleExecError, LoadDuplicateDefinitionError, LoadMissingClassError
from .loader import ConfigLoadNotFoundError, ConfigLoadInvalidUnicodeError, ConfigLoadSerdeError, ConfigLoadYAMLReaderError, ConfigLoadYAMLMarkedError
from .module import Connection, ModuleWrapper
from .validation import validate_acyclic, validate_no_static_deadlock

log = structlog.get_logger()

# Wrapper function to catch loader exceptions with custom event names
def load_catch_errs(name:str, paths:list[str]):
	try:
		return load_paths(paths)
	except LoadFileNotFoundError as e:
		log.fatal('harness.load.%s.file_not_found', name, plugin=e.plugin, file=e.file)
	except LoadInvalidSpecError as e:
		log.fatal('harness.load.%s.invalid_spec', name, plugin=e.plugin, file=e.file)
	except LoadMalformedSpecError as e:
		log.fatal('harness.load.%s.malformed_spec', name, plugin=e.plugin, file=e.file, exception=e.exception)
	except LoadSpecNoLoaderError as e:
		log.fatal('harness.load.%s.spec_no_loader', name, plugin=e.plugin, file=e.file)
	except LoadModuleExecError as e:
		log.fatal('harness.load.%s.module_exec_error', name, plugin=e.plugin, file=e.file, exception=e.exception)
	except LoadDuplicateDefinitionError as e:
		log.fatal('harness.load.%s.duplicate_def', name, plugin=e.plugin, file=e.file, key=e.key)
	except LoadMissingClassError as e:
		log.fatal('harness.load.%s.missing_class', name, plugin=e.plugin, file=e.file, mod=e.module_name, class_=e.class_name)
	except ConfigLoadNotFoundError as e:
		log.fatal('harness.load.config.%s.not_found', name, file=e.path)
	except ConfigLoadInvalidUnicodeError as e:
		log.fatal('harness.load.config.%s.invalid_unicode', name, file=e.path, reason=e.reason, invalid_slice=e.invalid_slice)
	except ConfigLoadSerdeError as e:
		log.fatal('harness.load.config.%s.serde', name, file=e.path)
	except ConfigLoadYAMLReaderError as e:
		log.fatal('harness.load.config.%s.yaml_read', name, file=e.path, error_name=e.name, position=e.position, character=e.character, encoding=e.encoding, reason=e.reason)
	except ConfigLoadYAMLMarkedError as e:
		log.fatal('harness.load.config.%s.yaml_marked', name, file=e.path, problem=e.problem, problem_mark=e.problem_mark)
	except Exception as e:
		log.fatal('harness.load.%s.exception', name, exception=e)

@dataclass
class Graph:
	nodes: dict[str, ModuleWrapper]

	def __init__(self):
		self.nodes = {}

	@staticmethod
	def from_file(path:str) -> Graph:
		try:
			config = load_config_file(GraphConfig, Path(path))
			return Graph.from_config(config)
		except ConfigLoadNotFoundError as e:
			log.fatal('harness.config.not_found', file=e.path)
		except ConfigLoadInvalidUnicodeError as e:
			log.fatal('harness.config.invalid_unicode', file=e.path, reason=e.reason, invalid_slice=e.invalid_slice)
		except ConfigLoadSerdeError as e:
			log.fatal('harness.config.serde', file=e.path)
		except ConfigLoadYAMLReaderError as e:
			log.fatal('harness.config.yaml_read', file=e.path, error_name=e.name, position=e.position, character=e.character, encoding=e.encoding, reason=e.reason)
		except ConfigLoadYAMLMarkedError as e:
			log.fatal('harness.config.yaml_marked', file=e.path, problem=e.problem, problem_mark=e.problem_mark)
		except Exception as e:
			log.fatal('harness.config.exception', exception=e)

	@staticmethod
	def from_config(config:GraphConfig) -> Graph:
		graph = Graph()

		# Dynamically load plugins
		module_mappings = load_catch_errs('module', config.modules)
		contract_mappings = load_catch_errs('contract', config.contracts)

		# Validate modules have run functions
		missing_runs = [ name for (name, mod) in module_mappings.items() if not hasattr(mod, 'run') ]
		if len(missing_runs) > 0:
			log.fatal("harness.load.module.missing_fns", names=missing_runs)

		# Validate contracts have get_inputs functions
		missing_get_inputs = [ name for (name, contract) in contract_mappings.items() if not hasattr(contract, 'get_inputs') ]
		if len(missing_get_inputs) > 0:
			log.fatal("harness.load.contract.missing_fns", names=missing_get_inputs)

		# Initialise the nodes in the graph
		errors = False
		for i, node in enumerate(config.nodes):
			if node.id in graph.nodes:
				log.error('harness.graph.node.duplicate', index=i, id=node.id)
				errors = True
			else:
				has_error = False
				if not node.module in module_mappings:
					log.error('harness.graph.node.invalid_module', index=i, id=node.id, mod=node.module)
					has_error = True

				if node.contract != '' and not node.contract in contract_mappings:
					log.error('harness.graph.node.invalid_contract', index=i, id=node.id, contract=node.contract)
					has_error = True

				if not has_error:
					contract = contract_mappings[node.contract] if node.contract != '' else DefaultContract
					graph.nodes[node.id] = ModuleWrapper(id=node.id, Module=module_mappings[node.module], config=node.config, Contract=contract, contract_config=node.contract_config)
				else:
					errors = True

		if errors:
			log.fatal('harness.graph.invalid_nodes')

		# Initialise the edges in the graph
		errors = False
		source_tracker = {} # Verify each dst only has one source
		consumption = [ False for _ in config.edges ] # Keep track of edge usage
		for id, node in graph.nodes.items():
			dsts = []
			for (i, edge) in enumerate(config.edges):
				if edge.src.node == id:
					if edge.dst.node not in graph.nodes:
						log.error('harness.graph.edge.invalid_dst', edge=edge)
						consumption[i] = True
						errors = True
						continue

					# Validate src/dst ports
					consumption[i] = True
					has_error = False
					dst_name = graph.nodes[edge.dst.node].get_canonical_port(edge.dst.port)
					if dst_name is None:
						has_error = True
						log.error('harness.graph.edge.invalid_dst_port', edge=edge)

					if edge.src.port not in node.structure.emits and node.structure.definite_emits:
						has_error = True
						log.error('harness.graph.edge.invalid_src_port', edge=edge)

					if has_error:
						errors = True
						continue

					if not node.structure.definite_emits:
						log.warn('harness.graph.node.non_definite_emits', node=node)

					dsts.append(Connection(edge.src.port, graph.nodes[edge.dst.node], dst_name))

					# Source tracking
					key = (edge.dst.node, dst_name)
					if not key in source_tracker:
						source_tracker[key] = 1
					else:
						source_tracker[key] += 1

			dsts.sort(key=lambda conn: conn.self_port)
			node.set_dsts(dsts)

		if errors:
			log.fatal('harness.graph.invalid_edges')

		# Validate each src only accepts one connection
		node_ports = [ (node, port) for ((node, port), n) in source_tracker.items() if n > 1 ]
		if len(node_ports) > 0:
			log.fatal('harness.graph.overloaded_srcs', node_ports=node_ports)

		# Validate all edges are consumed (non-fatal)
		unused_edges = [ config.edges[i] for (i, used) in enumerate(consumption) if not used ]
		if len(unused_edges) > 0:
			log.warn('harness.graph.unused_edges', edges=unused_edges)

		# Validate the graph is acyclic
		cyclic_nodes = [ name for name in validate_acyclic(config) if name is not None ]
		if len(cyclic_nodes) > 0:
			log.fatal('harness.graph.not_acyclic', cyclic_nodes=cyclic_nodes)

		# Static validation of the graph edges
		static_validation_res = validate_no_static_deadlock(graph)
		# 1. Every first-run-required input must have an incoming edge.
		if len(static_validation_res.edgeless_inputs) > 0:
			log.error('harness.graph.edgeless_inputs', nodes=static_validation_res.edgeless_inputs)
		# 2. At least one node must be source-capable.
		if not static_validation_res.has_source_capable:
			log.error('harness.graph.no_source')
		# 3. Every node must be reachable from some source-capable node.
		if len(static_validation_res.non_reachable_nodes) > 0:
			log.error('harness.graph.non_reachable_nodes', nodes=static_validation_res.non_reachable_nodes)

		if static_validation_res.has_error():
			log.fatal('harness.graph.has_deadlock')

		return graph

	# Run graph
	async def run(self):
		runs = [ node.run() for node in self.nodes.values() ]
		await asyncio.gather(*runs)
