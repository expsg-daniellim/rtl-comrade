from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import inspect
from inspect import Parameter
from serde import from_dict, SerdeError
from serde.compat import UserError
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
import typing

from .api import Payload, EndSentinel, ContractPort, NoDefaultError
from .port import Port, InvalidEnqueuedError
from .structure import ModuleStructure
from .structure import StructureInvalidTupleError, StructureNonStrPortNameError

log = structlog.get_logger()

@dataclass(frozen=True, slots=True)
class Connection:
	self_port: str
	other_node: ModuleWrapper
	other_port: str

class ModuleWrapper:
	def __init__(self, id:str, Module, config:dict, Contract, contract_config:dict|None=None):
		self.id = id

		if contract_config is None:
			contract_config = {}

		# Initialise Module (with config/id if available/supported)
		module_init_sig = inspect.signature(Module.__init__)
		module_init_args = {}
		if 'config' in module_init_sig.parameters:
			if hasattr(Module, 'Config'):
				try:
					config = from_dict(Module.Config, config)
				except SerdeError as e:
					log.fatal('config.deserialise.serde_error', context='harness.node.module', node=self.id, module=Module.__name__)
				except UserError as e:
					log.fatal('config.deserialise.user_error', context='harness.node.module', node=self.id, module=Module.__name__)
			else:
				log.warn('config.mismatch', context='harness.node.module', node=self.id, module=Module.__name__)

			module_init_args['config'] = config

		if 'id' in module_init_sig.parameters:
			module_init_args['id'] = self.id + '.module'

		try:
			self.module = Module(**module_init_args)
		except Exception as e:
			log.fatal('init', context='harness.node.module', node=self.id, module=Module.__name__, exc_info=e)

		# Initialise ports
		bind_contextvars(context='harness.node.module.source', node=self.id, module=Module.__name__)
		try:
			self.structure = ModuleStructure(Module)
		except StructureInvalidTupleError as e:
			unbind_contextvars('context')
			log.fatal('invalid_tuple', context='harness.node.module.emits', tuple_=e.tuple_)
		except StructureNonStrPortNameError as e:
			unbind_contextvars('context')
			log.fatal('invalid_port_name', context='harness.node.module.emits', port=e.port_name)
		finally:
			unbind_contextvars('context', 'node', 'module')

		self.ports = OrderedDict({ arg.name: Port.from_structure(arg) for arg in self.structure.args })

		# Initialise Contract with available init params
		contract_init_sig = inspect.signature(Contract.__init__)
		contract_init_args = {}

		if 'config' in contract_init_sig.parameters:
			if hasattr(Contract, 'Config'):
				try:
					contract_config = from_dict(Contract.Config, contract_config)
				except SerdeError as e:
					log.fatal('config.deserialise.serde_error', context='harness.node.contract', node=self.id, contract=Contract.__name__)
				except UserError as e:
					log.fatal('config.deserialise.user_error', context='harness.node.contract', node=self.id, contract=Contract.__name__, exc_info=e)
			else:
				log.warn('config.mismatch', context='harness.node.contract', node=self.id, contract=Contract.__name__)

			contract_init_args['config'] = contract_config

		if 'id' in contract_init_sig.parameters:
			contract_init_args['id'] = self.id + '.contract'

		if 'ports' in contract_init_sig.parameters:
			contract_init_args['ports'] = { name: ContractPort(name=name, get=port.get, try_get=port.try_get, has_ended=port.has_ended, has_default=port.has_default, default=port.default) for (name, port) in self.ports.items() }
		else:
			# Warn for this one because it's a pretty pointless contract that has no input ports
			log.warn('init.no_ports', context='harness.node.contract', node=self.id, contract=Contract.__name__)

		try:
			self.contract = Contract(**contract_init_args)
		except Exception as e:
			log.fatal('init', context='harness.node.contract', node=self.id, contract=Contract.__name__, exc_info=e)

		# Initialise output targets (for future setting in set_dsts after edges are validated (which requires Node)
		self.dsts = None
		self.dst_counts = {}

	def set_dsts(self, dsts:list[Connection]):
		self.dsts = dsts

	def get_canonical_port(self, port:int|str) -> str|None:
		if type(port) is str and port in self.ports.keys():
			return port
		elif type(port) is int and port - 1 < len(self.ports) and port - 1 >= 0:
			return list(self.ports.keys())[port - 1]
		else:
			return None

	async def accept(self, val:Payload|EndSentinel, port:str):
		if port not in self.ports:
			log.error('no_port', context='harness.module.accept', node=self.id, port=port)
			return

		await self.ports[port].queue.put(val)

	async def process_result(self, res:tuple[str, typing.Any]|typing.Any):
		port, value = None, None

		# Specific outputs are specified by returning the tuple (<port name:str>, <value:Any>)
		if type(res) is tuple:
			if len(res) != 2:
				log.error('malformed_output', context='harness.module.res', port=res[0] if len(res) > 0 else None, data=res)
				return

			if type(res[0]) is not str:
				log.error('non_string_port', context='harness.module.res', port=res[0])
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
			log.info('no_destination', context='harness.module.res', port=port, data=value)

		for dst in dsts:
			key = (dst.other_node.id, dst.other_port)
			self.dst_counts[key] = self.dst_counts.get(key, -1) + 1
			payload = Payload(self.id, self.dst_counts[key], value)
			await dst.other_node.accept(val=payload, port=dst.other_port)

	async def run(self):
		inputs = {0} # Python has no do...while; dummy value to bootstrap loop
		while len(inputs) > 0: # Fancy method to ensure that nodes with no inputs only run once
			# Get inputs according to contract
			bind_contextvars(context='harness.node.contract', node=self.id, contract=type(self.contract).__name__)
			try:
				if inspect.iscoroutinefunction(self.contract.get_inputs):
					inputs = await self.contract.get_inputs()
				else:
					inputs = self.contract.get_inputs()
			except InvalidEnqueuedError as e:
				log.fatal('invalid_enqueued', context='harness.node.port', port=e.name, type_=e.type_)
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
			except Exception as e:
				log.fatal('exception', exc_info=e)
			finally:
				unbind_contextvars('context', 'node', 'module')

		if self.dsts is None:
			log.error('dsts.not_initialised', context='harness.module.res', node=self.id)
			return

		# Propogate EndSentinel
		for dst in self.dsts:
			await dst.other_node.accept(val=EndSentinel(self.id), port=dst.other_port)
