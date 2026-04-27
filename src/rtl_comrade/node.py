from asyncio import Queue
from collections import OrderedDict
from dataclasses import dataclass
import inspect
from inspect import signature, Parameter
from serde import serde, from_dict
import typing

from .config import GraphConfigPort

@dataclass
class Connection:
	self_port: int
	other_node: ModuleWrapper
	other_port: int

@dataclass
class Port:
	name: str
	queue: Queue
	persistent: bool
	has_default: bool
	default: typing.Any

	@staticmethod
	def from_param(param:Parameter, i:int, ports:dict[str|int, GraphConfigPort]):
		persistent = False
		if (i + 1) in ports:
			persistent = ports[i + 1].persistent
		elif param.name in ports:
			persistent = ports[param.name].persistent

		has_default = param.default is not Parameter.empty
		default = param.default if param.default is not Parameter.empty else None
		return Port(param.name, Queue(), persistent, has_default, default)

	async def get(self):
		val = await self.queue.get()

		if val is not None:
			self.last_value = val
		return val

	# Unravel special cases after normal ones come in
	async def get_special(self):
		if self.queue.empty():
			await self.queue.put(None)

		if self.persistent:
			return self.last_value
		elif self.has_default:
			return self.default
		else:
			return None

	def is_special(self):
		return self.persistent or self.has_default

# TODO: proper error handling (include info about originating module id)
# TODO: explicitly declare class members
class ModuleWrapper:
	def __init__(self, Module, id:str, config:dict, ports:dict[str|int, GraphConfigPort]):
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
			raise "module is not runnable"

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
			raise "invalid port type"

		await self.ports[port_name].queue.put(val)

	async def process_result(self, res:tuple[int|str, typing.Any]|typing.Any):
		port = res[0] if type(res) is tuple else 1
		value = res[1] if type(res) is tuple else res

		for dst in filter(lambda dst: dst.self_port == port, self.dsts):
			await dst.other_node.accept(val=value, port=dst.other_port)

	async def run(self):
		inputs = [0] # Dummy value to bootstrap loop
		while len(inputs) > 0:
			inputs = { port.name: await port.get() for port in self.ports.values() }
			inputs = { port.name: await port.get_special() if inputs[port.name] is None else inputs[port.name] for port in self.ports.values() }

			if any(i == None and not port.is_special() for (i, port) in zip(inputs.values(), self.ports.values())):
				if not all(i == None or port.is_special() for (i, port) in zip(inputs.values(), self.ports.values())):
					raise "mismatched end of inputs"
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
			raise f"dsts of {self.id} have not been initialised"

		for dst in self.dsts:
			await dst.other_node.accept(val=None, port=dst.other_port)
