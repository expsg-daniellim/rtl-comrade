"""Runtime node execution, contract invocation, and downstream dispatch."""

from __future__ import annotations
from collections import OrderedDict
import copy
from dataclasses import dataclass, field
from pathlib import Path
import inspect
from typing import Any, cast

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
	"""One outgoing connection from a source output port to a destination input.

	Attributes:
		self_port: The source output port name on the emitting node.
		other_node: The downstream destination node instance.
		other_port: The destination input port name on the downstream node.
	"""

	self_port: str
	other_node: Node
	other_port: str

@dataclass(slots=True)
class Node:
	"""A live runtime node binding together a module, contract, and input ports.

	Attributes:
		id: Runtime node id from graph configuration.
		module: Instantiated module object.
		structure: Parsed module structure derived from the module class.
		ports: Ordered input ports keyed by port name.
		contract: Instantiated contract object controlling scheduling.
		dsts: Outgoing downstream connections; ``None`` until ``set_dsts`` is called.
		dst_counts: Running message count per ``(node_id, port)`` destination pair.
		required_ports: Canonical names of input ports marked required in the graph config.
	"""

	id: str
	module: type[Any]
	structure: ModuleStructure
	ports: OrderedDict[str, Port]
	contract: type[Any]
	dsts: list[Connection]|None = None
	dst_counts: dict[tuple[str, str], int] = field(default_factory=dict)
	required_ports: set[str] = field(default_factory=set)

	def __init__(self, id:str, module:GraphModule, config:dict, Contract:type[Any], contract_config:dict|None=None, relative_path:Path=Path(), ports:OrderedDict[str, Port]|None=None, required_ports:list[int|str]|None=None):  # pylint: disable=redefined-builtin
		"""Instantiate one runtime node from a GraphModule descriptor and a contract class.

		Args:
			id: Runtime node id from graph configuration.
			module: Pre-validated GraphModule descriptor wrapping the module class.
			config: Module-specific configuration dictionary.
			Contract: Contract plugin class controlling this node's scheduling.
			contract_config: Optional contract-specific configuration dictionary.
			relative_path: Base path used to resolve ``{graph}``-relative config paths.
			ports: Override port mapping for non-definite-input modules; merged on top of the module's own ports.
			required_ports: Destination-port references (name or 1-based index) marked required in the graph config.

		Returns:
			None.
		"""

		self.id = id

		if contract_config is None:
			contract_config = {}

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

		# Initialise ports
		self.structure = module.structure # It's a reference, should be fine

		self.ports = copy.deepcopy(module.ports)
		if ports is not None:
			self.ports.update(ports)

		# Resolve config-declared required refs to canonical names; edge validation later reports unresolvable refs.
		self.required_ports = { name for ref in required_ports or [] if (name := self.get_canonical_port(ref)) is not None }

		# Initialise Contract with available init params
		try:
			contract_init_sig = inspect.signature(Contract.__init__)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', context='harness.node.contract', node=self.id, contract=Contract.__name__, exc_info=e)

		contract_init_args = {}

		if 'config' in contract_init_sig.parameters:
			if hasattr(Contract, 'Config'):
				try:
					contract_config = from_dict(Contract.Config, contract_config)

					# Relativise config paths (if not absolute)
					for (attr, val) in [ (attr, getattr(contract_config, attr)) for attr in dir(contract_config) if not callable(getattr(contract_config, attr)) and not (attr.startswith('__') and attr.endswith('__')) ]:
						if isinstance(val, Path) and not val.is_absolute() and val.parts[0] == '{graph}':
							setattr(contract_config, attr, relative_path / Path(*val.parts[1:]))
				except SerdeError as e:
					log.fatal('config.deserialise.serde_error', context='harness.node.contract', node=self.id, contract=Contract.__name__, exc_info=e)
				except UserError as e:
					log.fatal('config.deserialise.user_error', context='harness.node.contract', node=self.id, contract=Contract.__name__, exc_info=e)
			else:
				log.warn('config.mismatch', context='harness.node.contract', node=self.id, contract=Contract.__name__)

			contract_init_args['config'] = contract_config

		if 'id' in contract_init_sig.parameters:
			contract_init_args['id'] = self.id + '.contract'

		if 'ports' in contract_init_sig.parameters:
			contract_init_args['ports'] = { name: ContractPort(name=name, get=port.get, try_get=port.try_get, has_ended=port.has_ended, has_default=port.has_default, required=name in self.required_ports) for (name, port) in self.ports.items() }
		else:
			# Warn for this one because it's a pretty pointless contract that has no input ports
			log.warn('init.no_ports', context='harness.node.contract', node=self.id, contract=Contract.__name__)

		try:
			self.contract = Contract(**contract_init_args)
		except typer.Exit:
			raise
		except Exception as e:
			log.fatal('init', context='harness.node.contract', node=self.id, contract=Contract.__name__, exc_info=e)

		# Initialise output targets (for future setting in set_dsts after edges are validated (which requires Node)
		self.dsts = None
		self.dst_counts = {}

	def set_dsts(self, dsts:list[Connection]):
		"""Assign this node's validated downstream connections.

		Args:
			dsts: Validated outgoing connections from this node.

		Returns:
			None.
		"""

		self.dsts = dsts

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

	async def accept(self, val:Payload|EndSentinel, port:str):
		"""Enqueue an inbound runtime message onto one input port.

		Args:
			val: Incoming runtime message for this node.
			port: Canonical destination input-port name.

		Returns:
			None.
		"""

		if port not in self.ports:
			log.error('no_port', context='harness.module.accept', node=self.id, port=port)
			return

		await self.ports[port].queue.put(val)

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

		if self.dsts is None:
			log.error('dsts.not_initialised', context='harness.module.res')
			return

		dsts = [ dst for dst in self.dsts if dst.self_port == port ]
		if len(dsts) <= 0 and len(self.dsts) > 0:
			log.info('no_destination', context='harness.module.res', port=port, data_type=type(value).__name__, data_repr=repr(value))

		for dst in dsts:
			key = (dst.other_node.id, dst.other_port)
			self.dst_counts[key] = self.dst_counts.get(key, -1) + 1
			payload = Payload(self.id, self.dst_counts[key], value)
			await dst.other_node.accept(val=payload, port=dst.other_port)

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

		if self.dsts is None:
			log.error('dsts.not_initialised', context='harness.module.res', node=self.id)
			return

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

		# Propagate EndSentinel
		for dst in self.dsts:
			await dst.other_node.accept(val=EndSentinel(self.id), port=dst.other_port)
