"""Module descriptor wrapping a plugin class with pre-validated structure and port metadata."""

from __future__ import annotations
from collections import OrderedDict
import copy
from dataclasses import dataclass
import inspect
from typing import cast, Any, Self

import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .config import GraphConfigNode, GraphConfigEdge
from .logging import HarnessLogger, LogEvent
from .port import Port
from .structure import ModuleStructure
from .structure import StructureInvalidTupleError, StructureNonStrPortNameError

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass(slots=True)
class PortInvalidMappingTarget(Exception):
	"""Raised when a ``contract_port_mappings`` entry names a target port absent from the module's definite-input signature.

	Attributes:
		targets: The unresolvable target port names.
	"""

	targets: list[str]

@dataclass(slots=True)
class PortNonDefinitePositionalDestinationError(Exception):
	"""Raised when a positional (integer) destination port targets a non-definite-input module that has no declared port order.

	Attributes:
		ports: The positional port references that cannot be resolved.
	"""

	ports: list[int]

@dataclass(frozen=True, slots=True)
class GraphModule:
	name: str
	Module: type[Any]
	structure: ModuleStructure
	ports: OrderedDict[str, Port]
	has_id: bool
	has_config: bool
	defines_config: bool

	def construct_node_ports(self, node:GraphConfigNode, edges:list[GraphConfigEdge]) -> OrderedDict[str, Port]:
		"""Build the input-port surface for a node, choosing the strategy based on config and module definiteness.

		Contract-port mappings override the module signature; non-definite modules derive ports from incoming edges; definite modules deep-copy from the module's own port template.

		Args:
			node: The graph config node whose ports are being constructed.
			edges: All graph edges, filtered internally to those targeting this node.

		Returns:
			Ordered input ports keyed by port name.
		"""

		if node.contract_port_mappings is not None: # Config-defined mappings override everything
			invalid_targets = [ target for targets in node.contract_port_mappings.values() for target in targets if target not in self.ports ] if self.structure.definite_inputs else []
			if len(invalid_targets) > 0:
				raise PortInvalidMappingTarget(invalid_targets)

			# An empty target list forwards to nothing, so it cannot inherit a default
			return OrderedDict({ cport: Port(cport, has_default=len(targets) > 0 and all(name in self.ports and self.ports[name].has_default for name in targets)) for cport, targets in node.contract_port_mappings.items() })
		elif not self.structure.definite_inputs: # Non-definite inputs require special validation and construction
			# A positional port cannot be resolved against a non-definite surface that has no declared port order, so reject it before building the surface.
			positional_ports = [ edge.dst.port for edge in edges if edge.dst.node == node.id and not isinstance(edge.dst.port, str) ]
			if len(positional_ports) > 0:
				raise PortNonDefinitePositionalDestinationError(positional_ports)

			# Assemble port mappings from incoming edges for non-definite-input modules.
			return OrderedDict({ edge.dst.port: Port(edge.dst.port) for edge in edges if edge.dst.node == node.id and isinstance(edge.dst.port, str) })
		else:
			return copy.deepcopy(self.ports)


	@classmethod
	def from_module(cls, Module:type[Any]) -> Self:
		"""Build a validated GraphModule descriptor from a raw module class.

		Inspects ``Module.__init__`` to determine which harness-controlled parameters
		(``id``, ``config``) it accepts, validates the module's run-function structure,
		and pre-builds the canonical input-port mapping for definite-input modules.

		Args:
			Module: Module plugin class to wrap.

		Returns:
			A frozen GraphModule descriptor ready for use by PreNode.__init__.
		"""
		# Perform validation
		bind_contextvars(module=Module.__name__)

		try:
			module_init_sig = inspect.signature(Module.__init__)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', context='harness.module', exc_info=e)

		has_id = 'id' in module_init_sig.parameters
		defines_config = hasattr(Module, 'Config')
		has_config = 'config' in module_init_sig.parameters

		if has_config and not defines_config:
			log.warn('config.mismatch', context='harness.module') # Module has config in init but defines no Config class

		# structured validation
		try:
			structure = ModuleStructure(Module)
			if structure.definite_inputs:
				ports = OrderedDict({ arg.name: Port.from_structure(arg) for arg in structure.args })
			else:
				ports = OrderedDict()
		except StructureInvalidTupleError as e:
			log.fatal('invalid_tuple', context='harness.module.emits', lineno=e.lineno, tuple_=e.tuple_)
		except StructureNonStrPortNameError as e:
			log.fatal('invalid_port_name', context='harness.module.emits', lineno=e.lineno, port=str(e.port_name))
		finally:
			unbind_contextvars('module')

		return cls(name=Module.__name__, Module=Module, structure=structure, ports=ports, has_id=has_id, has_config=has_config, defines_config=defines_config)
