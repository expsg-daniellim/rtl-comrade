"""Module descriptor wrapping a plugin class with pre-validated structure and port metadata."""

from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import inspect
from typing import cast, Any, Self

import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .logging import HarnessLogger
from .port import Port
from .structure import ModuleStructure
from .structure import StructureInvalidTupleError, StructureNonStrPortNameError

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass(frozen=True, slots=True)
class GraphModule:
	name: str
	Module: type[Any]
	structure: ModuleStructure
	ports: OrderedDict[str, Port]
	has_id: bool
	has_config: bool
	defines_config: bool

	@classmethod
	def from_module(cls, Module:type[Any]) -> Self:
		"""Build a validated GraphModule descriptor from a raw module class.

		Inspects ``Module.__init__`` to determine which harness-controlled parameters
		(``id``, ``config``) it accepts, validates the module's run-function structure,
		and pre-builds the canonical input-port mapping for definite-input modules.

		Args:
			Module: Module plugin class to wrap.

		Returns:
			A frozen GraphModule descriptor ready for use by Node.__init__.
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
