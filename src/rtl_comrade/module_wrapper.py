from asyncio import Queue
from collections import OrderedDict
from dataclasses import dataclass
import inspect
from inspect import signature, Parameter
from serde import serde, from_dict
import typing

from .config import GraphConfigNodePort

@dataclass
class Connection:
	self_port: int
	other_node: ModuleWrapper
	other_port: int

class PortError(Exception):
	def __init__(self, id, message):
		super().__init__(self, message)
		self.message = message
		self.id = id

	def __str__(self):
		return f"{self.id}: {self.message}"

# TODO: clean up typing with generics
@dataclass
class Port:
	name: str
	queue: Queue
	persistent: bool
	has_default: bool
	default: typing.Any
	last_value: typing.Any = None

	@staticmethod
	def from_param(param:Parameter, i:int, ports:dict[str|int, GraphConfigNodePort]):
		persistent = False
		if (i + 1) in ports:
			persistent = ports[i + 1].persistent
		elif param.name in ports:
			persistent = ports[param.name].persistent

		has_default = param.default is not Parameter.empty
		default = param.default if param.default is not Parameter.empty else None
		return Port(param.name, Queue(), persistent, has_default, default)

	async def get(self) -> typing.Any | None:
		return await self.queue.get()

	# Unravel special cases after normal ones come in
	async def get_special(self):
		if not self.is_special():
			raise PortError(self.name, "get_special on non-special")

		val = None
		try:
			val = self.queue.get_nowait()
			if val is not None:
				self.last_value = val
			else:
				await self.queue.put(val)
		except asyncio.QueueEmpty:
			pass

		if val is not None:
			return val
		elif self.persistent:
			return self.last_value
		elif self.has_default:
			return self.default
		else:
			raise PortError(self.name, "unsupported special case")

	def is_special(self):
		return self.persistent or self.has_default

class ModuleError(Exception):
	def __init__(self, id, message):
		super().__init__(self, message)
		self.message = message
		self.id = id

	def __str__(self):
		return f"{self.id}: {self.message}"

class ModuleWrapper:
	def __init__(self, Module, id:str, config:dict, ports:dict[str|int, GraphConfigNodePort]):
		self.id = id
		# TODO: warn about config acceptance
		init_sig = signature(Module.__init__)

		if 'config' in init_sig.parameters:
			if hasattr(Module, 'Config'):
				config = from_dict(Module.Config, config)
			self.module = Module(config=config)
		else:
			self.module = Module()

		if not hasattr(self.module, 'run'):
			raise ModuleError(self.id, "module is not runnable")

		run_sig = signature(self.module.run)
		self.ports = OrderedDict({ name: Port.from_param(param, i, ports) for (i, (name, param)) in enumerate(run_sig.parameters.items()) })

	def set_dsts(self, dsts:list[Connection]):
		self.dsts = dsts

	async def accept(self, val:typing.Any, port:str|int=1):
		port_name = None
		if type(port) is str and port in self.ports.keys():
			port_name = port
		elif type(port) is int and port - 1 < len(self.ports) and port - 1 >= 0:
			port_name = list(self.ports.keys())[port - 1]
		else:
			raise ModuleError(self.id, "invalid port type")

		await self.ports[port_name].queue.put(val)

	async def process_result(self, res:tuple[int|str, typing.Any]|typing.Any):
		port = res[0] if type(res) is tuple else 1
		value = res[1] if type(res) is tuple else res

		for dst in filter(lambda dst: dst.self_port == port, self.dsts):
			await dst.other_node.accept(val=value, port=dst.other_port)

	async def run(self):
		inputs = {0} # Python has no do...while; dummy value to bootstrap loop
		while len(inputs) > 0: # Fancy method to ensure that nodes with no inputs only run once
			# Get required inputs
			inputs = { port.name: await port.get() for port in self.ports.values() if not port.is_special() }
			# Get special inputs
			inputs |= { port.name: await port.get_special() for port in self.ports.values() if port.is_special() }

			if any(i == None and not port.is_special() for (i, port) in zip(inputs.values(), self.ports.values())):
				if not all(i == None or port.is_special() for (i, port) in zip(inputs.values(), self.ports.values())):
					raise ModuleError(self.id, "mismatched end of inputs")
				break

			res = None
			if inspect.iscoroutinefunction(self.module.run):
				res = await self.module.run(**inputs)
			else:
				res = self.module.run(**inputs)

			if res is not None:
				if inspect.isgenerator(res):
					for r in res:
						await self.process_result(r)
				else:
					await self.process_result(res)
		
		if self.dsts is None:
			raise ModuleError(self.id, "dsts have not been initialised")

		for dst in self.dsts:
			await dst.other_node.accept(val=None, port=dst.other_port)
