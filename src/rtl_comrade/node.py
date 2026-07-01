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

from .api import Payload, EndSentinel, ContractPort
from .logging import HarnessLogger
from .module import GraphModule
from .port import Port, InvalidEnqueuedError
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
		Contract: Contract plugin class, instantiated when the Node is built.
		contract_config: Contract-specific configuration dictionary.
		relative_path: Base path used to resolve ``{graph}``-relative config paths.
	"""

	id: str
	module: type[Any]
	structure: ModuleStructure
	ports: OrderedDict[str, Port]
	definite_inputs: bool
	required_ports: set[str]
	Contract: type[Any]
	contract_config: dict
	relative_path: Path

	def __init__(self, id:str, module:GraphModule, config:dict, Contract:type[Any], *, contract_config:dict|None=None, relative_path:Path=Path(), ports:OrderedDict[str, Port]|None=None, required_ports:list[int|str]|None=None, definite_inputs_override:bool=False):  # pylint: disable=redefined-builtin,too-many-arguments
		"""Build the module and input ports, and retain the contract recipe for later.

		Args:
			id: Runtime node id from graph configuration.
			module: Pre-validated GraphModule descriptor wrapping the module class.
			config: Module-specific configuration dictionary.
			Contract: Contract plugin class controlling this node's scheduling.
			contract_config: Optional contract-specific configuration dictionary.
			relative_path: Base path used to resolve ``{graph}``-relative config paths.
			ports: Replacement input-port surface; when given, it becomes the node's ports outright instead of the module's own. Used for non-definite-input modules (built from incoming edges) and for ``contract_port_mappings`` nodes (the contract-port surface).
			required_ports: Destination-port references (name or 1-based index) marked required in the graph config.
			definite_inputs_override: When ``True``, forces the node's input surface to be treated as definite regardless of the module; ``False`` inherits ``module.structure.definite_inputs``. Definiteness only ever widens, so there is no need to force it off.

		Returns:
			None.
		"""

		self.id = id
		self.Contract = Contract
		self.contract_config = contract_config if contract_config is not None else {}
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
	"""A live runtime node binding together a module, contract, input ports, and outgoing connections.

	Constructed complete via ``from_prenode``; its structure is immutable (only ``dst_counts`` entries mutate at runtime).

	Attributes:
		id: Runtime node id from graph configuration.
		module: Instantiated module object.
		structure: Parsed module structure derived from the module class.
		ports: Ordered input ports keyed by port name.
		contract: Instantiated contract object controlling scheduling.
		definite_inputs: Whether the node's input surface is a known finite set.
		required_ports: Canonical names of input ports marked required in the graph config.
		dsts: Destination Ports grouped by the source output port name that feeds them.
		dst_counts: Sent-payload counters parallel to each ``dsts`` port list, keyed the same way.
	"""

	id: str
	module: type[Any]
	structure: ModuleStructure
	ports: OrderedDict[str, Port]
	contract: type[Any]
	definite_inputs: bool
	required_ports: set[str]
	dsts: dict[str, list[Port]]
	dst_counts: dict[str, list[int]] = field(default_factory=dict)

	@classmethod
	def from_prenode(cls, pre:PreNode, dsts:dict[str, list[Port]], input_labels:dict[str, frozenset]) -> Self:
		"""Couple a PreNode with its edge information to produce the finished runtime Node.

		Constructs the contract from the PreNode's ports — now that their control-dependence labels are known — so the
		contract owns its ContractPorts outright, with ``branch_labels`` injected from ``input_labels``.

		Args:
			pre: The constructed PreNode.
			dsts: Destination Ports grouped by the source output port name that feeds them.
			input_labels: Control-dependence labels per input-port name, from graph propagation.

		Returns:
			The finished Node.
		"""

		try:
			contract_init_sig = inspect.signature(pre.Contract.__init__)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', context='harness.node.contract', node=pre.id, contract=pre.Contract.__name__, exc_info=e)

		contract_config = pre.contract_config
		contract_init_args:dict[str, Any] = {}

		if 'config' in contract_init_sig.parameters:
			if hasattr(pre.Contract, 'Config'):
				try:
					contract_config = from_dict(pre.Contract.Config, contract_config)

					# Relativise config paths (if not absolute)
					for (attr, val) in [ (attr, getattr(contract_config, attr)) for attr in dir(contract_config) if not callable(getattr(contract_config, attr)) and not (attr.startswith('__') and attr.endswith('__')) ]:
						if isinstance(val, Path) and not val.is_absolute() and val.parts[0] == '{graph}':
							setattr(contract_config, attr, pre.relative_path / Path(*val.parts[1:]))
				except SerdeError as e:
					log.fatal('config.deserialise.serde_error', context='harness.node.contract', node=pre.id, contract=pre.Contract.__name__, exc_info=e)
				except UserError as e:
					log.fatal('config.deserialise.user_error', context='harness.node.contract', node=pre.id, contract=pre.Contract.__name__, exc_info=e)
			else:
				log.warn('config.mismatch', context='harness.node.contract', node=pre.id, contract=pre.Contract.__name__)

			contract_init_args['config'] = contract_config

		if 'id' in contract_init_sig.parameters:
			contract_init_args['id'] = pre.id + '.contract'

		if 'ports' in contract_init_sig.parameters:
			contract_init_args['ports'] = { name: ContractPort(name=name, get=port.get, try_get=port.try_get, has_ended=port.has_ended, has_default=port.has_default, required=name in pre.required_ports, branch_labels=input_labels.get(name, frozenset())) for (name, port) in pre.ports.items() }
		else:
			# Warn for this one because it's a pretty pointless contract that has no input ports
			log.warn('init.no_ports', context='harness.node.contract', node=pre.id, contract=pre.Contract.__name__)

		try:
			contract = pre.Contract(**contract_init_args)
		except typer.Exit:
			raise
		except Exception as e:
			log.fatal('init', context='harness.node.contract', node=pre.id, contract=pre.Contract.__name__, exc_info=e)

		return cls(id=pre.id, module=pre.module, structure=pre.structure, ports=pre.ports, contract=contract, definite_inputs=pre.definite_inputs, required_ports=pre.required_ports, dsts=dsts, dst_counts={ port: [ 0 for _ in ports ] for port, ports in dsts.items() })

	async def process_result(self, res:tuple[str, Any]|Any):
		"""Normalize one module output and forward it to matching downstream edges.

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

		matched = self.dsts.get(port, [])
		if len(matched) == 0 and len(self.dsts) > 0:
			log.info('no_destination', context='harness.module.res', port=port, data_type=type(value).__name__, data_repr=repr(value))

		counts = self.dst_counts.get(port, [])
		for (i, dst_port) in enumerate(matched):
			payload = Payload(self.id, counts[i], value)
			counts[i] += 1
			await dst_port.queue.put(payload)

	async def run(self):
		"""Execute this node until its contract indicates termination.

		Returns:
			None.
		"""

		while True: # Fancy method to ensure that nodes with no inputs only run once
			# Get inputs according to contract
			bind_contextvars(context='harness.node.contract', node=self.id, contract=type(self.contract).__name__)
			try:
				if inspect.iscoroutinefunction(self.contract.get_inputs):
					inputs = await self.contract.get_inputs()
				else:
					inputs = self.contract.get_inputs()
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

			# Break out input Payloads into straight kwargs
			inputs = { name: i.payload for (name, i) in inputs.items() }

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
