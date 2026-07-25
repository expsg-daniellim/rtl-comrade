"""Runtime node execution, contract invocation, and downstream dispatch."""

from __future__ import annotations
from collections import OrderedDict
import copy
from dataclasses import dataclass, field
from pathlib import Path
import inspect
from typing import Any, cast, Self

from serde import from_dict, SerdeError
from serde.compat import UserError
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
import typer

from .api import Payload, EndSentinel
from .contract import ContractDefinitions
from .logging import HarnessLogger
from .module import GraphModule
from .port import Port, InvalidEnqueuedError, IllegalGetAccessError
from .structure import ModuleStructure

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

@dataclass(frozen=True, slots=True)
class Connection:
	"""One outgoing edge in id space, from a source output port to a destination input port.

	A construction-time value: it carries node identity (``other_node``) so deadlock validation and label propagation can
	work over ids, and it names the destination port so the runtime ``self_port -> [Port]`` map can be materialised from it.

	Attributes:
		self_port: Source output port name on the emitting node.
		other_node: Destination node id.
		other_port: Canonical destination input port name.
	"""

	self_port: str
	other_node: str
	other_port: str

@dataclass(slots=True)
class PreNode:  # pylint: disable=too-many-instance-attributes
	"""A node under construction: everything needed to validate edges and to build the runtime Node, minus its outgoing edges.

	Built in one pass from a config node. Its ``ports`` are the same objects that flow into the runtime Node, so an
	upstream ``Connection`` targeting one of them reaches the exact queue the node reads.

	Attributes:
		id: Runtime node id from graph configuration.
		module: Instantiated module object.
		structure: Parsed module structure derived from the module class.
		ports: Ordered input ports keyed by port name.
		definite_inputs: Whether the node's input surface is a known finite set.
		required_ports: Canonical names of input ports marked required in the graph config.
		contract_definitions: Resolved contract classes and their configs, instantiated when the Node is built.
		relative_path: Base path used to resolve ``{graph}``-relative config paths.
	"""

	id: str
	module: type[Any]
	structure: ModuleStructure
	ports: OrderedDict[str, Port]
	definite_inputs: bool
	required_ports: set[str]
	contract_definitions: ContractDefinitions
	relative_path: Path

	def __init__(self, id:str, module:GraphModule, config:dict, contract_definitions:ContractDefinitions, *, relative_path:Path=Path(), ports:OrderedDict[str, Port]|None=None, required_ports:list[int|str]|None=None, definite_inputs_override:bool=False):  # pylint: disable=redefined-builtin,too-many-arguments
		"""Build the module and input ports, and retain the contract recipes for later.

		Args:
			id: Runtime node id from graph configuration.
			module: Pre-validated GraphModule descriptor wrapping the module class.
			config: Module-specific configuration dictionary.
			contract_definitions: Resolved contract classes and their configs, governing this node's scheduling and output processing.
			relative_path: Base path used to resolve ``{graph}``-relative config paths.
			ports: Replacement input-port surface; when given, it becomes the node's ports outright instead of the module's own. Used for non-definite-input modules (built from incoming edges) and for ``contract_port_mappings`` nodes (the contract-port surface).
			required_ports: Destination-port references (name or 1-based index) marked required in the graph config.
			definite_inputs_override: When ``True``, forces the node's input surface to be treated as definite regardless of the module; ``False`` inherits ``module.structure.definite_inputs``. Definiteness only ever widens, so there is no need to force it off.

		Returns:
			None.
		"""

		self.id = id
		self.contract_definitions = contract_definitions
		self.relative_path = relative_path

		# Initialise Module (with config/id if available/supported)
		module_init_args:dict[str, Any] = {}
		if module.has_config:
			if module.defines_config:
				try:
					config = from_dict(module.Module.Config, config)

					# Relativise config paths (if not absolute)
					for (attr, val) in [ (attr, getattr(config, attr)) for attr in dir(config) if not callable(getattr(config, attr)) and not (attr.startswith('__') and attr.endswith('__')) ]:
						if isinstance(val, Path) and not val.is_absolute() and val.parts[0] == '{graph}':
							setattr(config, attr, relative_path / Path(*val.parts[1:]))
				except SerdeError as e:
					log.fatal('config.deserialise.serde_error', context='harness.node.module', node=self.id, module=module.name, exc_info=e)
				except UserError as e:
					log.fatal('config.deserialise.user_error', context='harness.node.module', node=self.id, module=module.name, exc_info=e)

			module_init_args['config'] = config

		if module.has_id:
			module_init_args['id'] = self.id + '.module'

		try:
			self.module = module.Module(**module_init_args)
		except typer.Exit:
			raise
		except Exception as e:
			log.fatal('init', context='harness.node.module', node=self.id, module=module.name, exc_info=e)

		self.structure = module.structure # It's a reference, should be fine
		self.definite_inputs = definite_inputs_override or module.structure.definite_inputs

		# A given surface replaces the module's own ports outright (contract-port surface or edge-derived non-definite ports).
		self.ports = ports if ports is not None else copy.deepcopy(module.ports)

		# Resolve config-declared required refs to canonical names; edge validation later reports unresolvable refs.
		self.required_ports = { name for ref in required_ports or [] if (name := self.get_canonical_port(ref)) is not None }

	def get_canonical_port(self, port:int|str) -> str|None:
		"""Resolve a destination port reference to its canonical string name.

		Args:
			port: Destination port addressed by name or 1-based position.

		Returns:
			The canonical destination input-port name, or ``None`` if invalid.
		"""

		if isinstance(port, str) and port in self.ports.keys():
			return port

		if isinstance(port, int) and port - 1 < len(self.ports) and port - 1 >= 0:
			return list(self.ports.keys())[port - 1]

		return None

@dataclass(frozen=True, slots=True)
class Node:  # pylint: disable=too-many-instance-attributes
	"""A live runtime node binding together a module, its contracts, input ports, and outgoing connections.

	Constructed complete via ``from_prenode``; its structure is immutable (only ``dst_counts`` entries mutate at runtime).

	A contract wraps both ends of the module. ``contract`` serves whichever end has no override: it supplies inputs
	through ``get_inputs``, and processes outputs too if it defines ``process_outputs``. ``input_contract`` and
	``output_contract`` displace it on their own end when set.

	Attributes:
		id: Runtime node id from graph configuration.
		module: Instantiated module object.
		structure: Parsed module structure derived from the module class.
		ports: Ordered input ports keyed by port name.
		contract: Instantiated general contract object, used on each end that is not overridden.
		input_contract: Instantiated contract supplying inputs in place of ``contract``, or ``None``.
		output_contract: Instantiated contract processing outputs in place of ``contract``, or ``None``.
		definite_inputs: Whether the node's input surface is a known finite set.
		required_ports: Canonical names of input ports marked required in the graph config.
		dsts: Destination Ports grouped by the source output port name that feeds them.
		dst_counts: Sent-payload counters parallel to each ``dsts`` port list, keyed the same way.
	"""

	id: str
	module: Any
	structure: ModuleStructure
	ports: OrderedDict[str, Port]
	contract: Any
	input_contract: Any
	output_contract: Any
	definite_inputs: bool
	required_ports: set[str]
	dsts: dict[str, list[Port]]
	dst_counts: dict[str, list[int]] = field(default_factory=dict)

	@classmethod
	def from_prenode(cls, pre:PreNode, dsts:dict[str, list[Port]], input_labels:dict[str, frozenset]) -> Self:
		"""Couple a PreNode with its edge information to produce the finished runtime Node.

		Constructs the node's contracts from the PreNode's ports — now that their control-dependence labels are known —
		so they own their ContractPorts outright, with ``branch_labels`` injected from ``input_labels``.

		Args:
			pre: The constructed PreNode.
			dsts: Destination Ports grouped by the source output port name that feeds them.
			input_labels: Control-dependence labels per input-port name, from graph propagation.

		Returns:
			The finished Node.
		"""

		contract, input_contract, output_contract = pre.contract_definitions.construct(pre.id, pre.ports, input_labels, pre.required_ports, pre.relative_path)

		return cls(id=pre.id, module=pre.module, structure=pre.structure, ports=pre.ports, contract=contract, input_contract=input_contract, output_contract=output_contract, definite_inputs=pre.definite_inputs, required_ports=pre.required_ports, dsts=dsts, dst_counts={ port: [ 0 for _ in ports ] for port, ports in dsts.items() })

	async def process_result(self, res:tuple[str, Any]|Any):
		"""Normalize one module output, pass it through the output contract, and forward it to matching downstream edges.

		The output contract's ``process_outputs`` sees the resolved port name and value and returns the value actually
		sent downstream. It cannot read the node's input ports: they are disabled outside ``get_inputs``.

		Args:
			res: One module return or yielded value in any supported output form.

		Returns:
			None.
		"""

		port, value = None, None

		# Specific outputs are specified by returning the tuple (<port name:str>, <value:Any>)
		if isinstance(res, tuple):
			if len(res) != 2:
				log.error('malformed_output', context='harness.module.res', port=str(res[0]) if len(res) > 0 else None, data_type=type(res).__name__, data_repr=repr(res))
				return

			if not isinstance(res[0], str):
				log.error('non_string_port', context='harness.module.res', port=str(res[0]))
				return

			port, value = res
		elif res is not None:
			port = 'default'
			value = res
		else:
			return

		# Apply output contract processing
		active_contract = self.output_contract if self.output_contract is not None else self.contract if hasattr(self.contract, 'process_outputs') and callable(getattr(self.contract, 'process_outputs')) else None
		if active_contract is not None:
			bind_contextvars(context='harness.node.contract', node=self.id, contract=type(active_contract).__name__)
			try:
				if inspect.iscoroutinefunction(active_contract.process_outputs):
					value = await active_contract.process_outputs(port, value)
				else:
					value = active_contract.process_outputs(port, value)
			except IllegalGetAccessError as e:
				log.fatal('illegal_get_access', context='harness.node.port', port=e.name, type_=e.type_)
			except typer.Exit:
				raise
			except Exception as e:
				# exc_info to make use of structlog's native exception handling
				log.fatal('exception', exc_info=e)
			finally:
				unbind_contextvars('context', 'node', 'contract')

		matched = self.dsts.get(port, [])
		if len(matched) == 0 and len(self.dsts) > 0:
			log.info('no_destination', context='harness.module.res', port=port, data_type=type(value).__name__, data_repr=repr(value))

		counts = self.dst_counts.get(port, [])
		for (i, dst_port) in enumerate(matched):
			payload = Payload(self.id, counts[i], value)
			counts[i] += 1
			await dst_port.queue.put(payload)

	async def run(self):
		"""Execute this node until its input contract indicates termination.

		Input ports are readable only for the duration of each ``get_inputs()`` call, so a contract that stashes a port
		and reads it later fails loudly rather than stealing a payload from the next invocation.

		Returns:
			None.
		"""

		while True: # Fancy method to ensure that nodes with no inputs only run once
			# Get inputs according to contract
			active_contract = self.input_contract if self.input_contract is not None else self.contract
			bind_contextvars(context='harness.node.contract', node=self.id, contract=type(active_contract).__name__)
			try:
				for port in self.ports.values():
					port.get_enabled = True

				if inspect.iscoroutinefunction(active_contract.get_inputs):
					inputs = await active_contract.get_inputs()
				else:
					inputs = active_contract.get_inputs()

				for port in self.ports.values():
					port.get_enabled = False
			except InvalidEnqueuedError as e:
				log.fatal('invalid_enqueued', context='harness.node.port', port=e.name, type_=e.type_)
			except typer.Exit:
				raise
			except Exception as e:
				# exc_info to make use of structlog's native exception handling
				log.fatal('exception', exc_info=e)
			finally:
				unbind_contextvars('context', 'node', 'contract')

			# End upon receiving EndSentinel
			if isinstance(inputs, EndSentinel):
				break

			# Break out input Payloads into straight kwargs, keyed by the real run parameter name.
			inputs = { self.ports[name].param if name in self.ports else name: i.payload for (name, i) in inputs.items() }

			# Run module based on async/non-async
			bind_contextvars(context='harness.node.module', node=self.id, module=type(self.module).__name__)
			res = None
			try:
				if inspect.iscoroutinefunction(self.module.run): # async return
					res = await self.module.run(**inputs)
				else: # regular return
					res = self.module.run(**inputs)

				# Unravel all possible forms of output return
				if inspect.isasyncgen(res): # async yield
					async for r in res:
						await self.process_result(r)
				elif inspect.isgenerator(res): # regular yield
					for r in res:
						await self.process_result(r)
				else: # return (async/regular)
					await self.process_result(res)
			except typer.Exit:
				raise
			except Exception as e:
				log.fatal('exception', exc_info=e)
			finally:
				unbind_contextvars('context', 'node', 'module')

			# 0-len inputs indicate there is nothing to wait for
			if len(inputs) == 0:
				break

		# Run module.finalise (if present)
		if hasattr(self.module, "finalise") and callable(self.module.finalise):
			bind_contextvars(context="harness.node.module", node=self.id, module=type(self.module).__name__)
			try:
				if inspect.iscoroutinefunction(self.module.finalise):
					res = await self.module.finalise()
				else:
					res = self.module.finalise()

				# Unravel all possible forms of output return
				if inspect.isasyncgen(res): # async yield
					async for r in res:
						await self.process_result(r)
				elif inspect.isgenerator(res): # regular yield
					for r in res:
						await self.process_result(r)
				else: # return (async/regular)
					await self.process_result(res)
			except typer.Exit:
				raise
			except Exception as e:
				log.fatal('exception', exc_info=e)
			finally:
				unbind_contextvars('context', 'node', 'module')

		# Propagate EndSentinel to each destination port
		for ports in self.dsts.values():
			for dst_port in ports:
				await dst_port.queue.put(EndSentinel(self.id))
