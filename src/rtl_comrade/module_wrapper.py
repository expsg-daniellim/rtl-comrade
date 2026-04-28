from __future__ import annotations # Obsolete after 3.14
import asyncio
from asyncio import Queue
from collections import OrderedDict
from dataclasses import dataclass
import inspect
from inspect import signature, Parameter
from serde import serde, from_dict
import typing

from .config import GraphConfigNodePort

# TODO: clean up typing with generics
@dataclass(frozen=True, slots=True)
class Payload:
	source: str
	n: int
	payload: typing.Any

@dataclass(frozen=True, slots=True)
class EndSentinel:
	source: str

@dataclass(frozen=True, slots=True)
class Connection:
	self_port: str
	other_node: ModuleWrapper
	other_port: str

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
	queue: Queue[Payload|EndSentinel]
	persistent: bool
	has_default: bool
	default: typing.Any
	default_n: int = 0
	ended: bool = False
	last_value: Payload|None = None

	@staticmethod
	def from_param(param:Parameter, i:int, ports:dict[str|int, GraphConfigNodePort]) -> Port:
		persistent = False
		if (i + 1) in ports:
			persistent = ports[i + 1].persistent
		elif param.name in ports:
			persistent = ports[param.name].persistent

		has_default = param.default is not Parameter.empty
		default = param.default if param.default is not Parameter.empty else None
		return Port(param.name, Queue(), persistent, has_default, default)

	async def get(self) -> Payload|EndSentinel:
		val =  await self.queue.get()
		if not isinstance(val, EndSentinel):
			self.last_value = val
		else:
			self.ended = True

		return val

	# Unravel special cases after normal ones come in
	async def get_special(self) -> Payload:
		if not self.is_special():
			raise PortError(self.name, "get_special on non-special")

		val = None
		try:
			if not self.ended:
				val = self.queue.get_nowait()

				if not isinstance(val, EndSentinel):
					self.last_value = val
				else:
					self.ended = True
		except asyncio.QueueEmpty:
			pass

		if not isinstance(val, EndSentinel) and val is not None:
			return val
		elif self.persistent:
			if not isinstance(self.last_value, EndSentinel):
				return self.last_value
			elif self.has_default:
				self.last_value = Payload("_default", self.default_n, self.default)
				self.default_n += 1
				return self.last_value
			else:
				raise PortError(self.name, "persistent port has no last value")
		elif self.has_default:
			payload = Payload("_default", self.default_n, self.default)
			self.default_n += 1
			return payload
		else:
			raise PortError(self.name, "unsupported special case")

	def is_special(self):
		return (self.persistent and self.last_value is not None) or self.has_default

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
		await self.ports[port].queue.put(val)

	async def process_result(self, res:tuple[str, typing.Any]|typing.Any):
		port = res[0] if type(res) is tuple else 'default'
		value = res[1] if type(res) is tuple else res

		dsts = [ dst for dst in self.dsts if dst.self_port == port ]
		if len(dsts) <= 0:
			# TODO: log-level info when logging is up
			print(f"output port {port} has no destinations")

		for dst in dsts:
			key = (dst.other_node.id, dst.other_port)
			self.dst_counts[key] = self.dst_counts.get(key, -1) + 1
			payload = Payload(self.id, self.dst_counts[key], value)
			await dst.other_node.accept(val=payload, port=dst.other_port)

	async def run(self):
		inputs = {0} # Python has no do...while; dummy value to bootstrap loop
		while len(inputs) > 0: # Fancy method to ensure that nodes with no inputs only run once
			# Order of precedence: required (non-special)/persistent (first run) > persistent (cached) > persistent (default) > default
			# Get required inputs
			inputs = { port.name: await port.get() for port in self.ports.values() if not port.is_special() }
			# Evaluate required end sentinels first
			if any(port.ended for port in self.ports.values() if not port.is_special()):
				if not all(port.ended for port in self.ports.values() if not port.is_special()):
					raise ModuleError(self.id, "mismatched end of inputs")
				break

			# Get special inputs
			inputs |= { port.name: await port.get_special() for port in self.ports.values() if port.is_special() and not port.name in inputs }
			# Special inputs should never return None

			# Unravel payload
			inputs = { name: i.payload for (name, i) in inputs.items() }

			res = None
			if inspect.iscoroutinefunction(self.module.run):
				res = await self.module.run(**inputs)
			else:
				res = self.module.run(**inputs)

			if res is not None:
				if inspect.isasyncgen(res):
					async for r in res:
						await self.process_result(r)
				elif inspect.isgenerator(res):
					for r in res:
						await self.process_result(r)
				else:
					await self.process_result(res)
		
		if self.dsts is None:
			raise ModuleError(self.id, "dsts have not been initialised")

		for dst in self.dsts:
			await dst.other_node.accept(val=EndSentinel(self.id), port=dst.other_port)
