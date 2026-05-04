from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import inspect
from inspect import signature, Parameter
from serde import from_dict
import typing

from .contract import ContractWrapper
from .port import Payload, EndSentinel, Port
from .structure import ModuleStructure

@dataclass(frozen=True, slots=True)
class Connection:
	self_port: str
	other_node: ModuleWrapper
	other_port: str

class ModuleError(Exception):
	def __init__(self, id, message):
		super().__init__(self, message)
		self.message = message
		self.id = id

	def __str__(self):
		return f"{self.id}: {self.message}"

class ModuleWrapper:
	def __init__(self, id:str, Module, config:dict, Contract, contract_config:dict={}):
		self.id = id

		# Check Module is valid
		# TODO: warn about config acceptance
		init_sig = signature(Module.__init__)

		if 'config' in init_sig.parameters:
			if hasattr(Module, 'Config'):
				config = from_dict(Module.Config, config)
			self.module = Module(config=config)
		else:
			self.module = Module()

		if not hasattr(self.module, 'run') or not inspect.isroutine(self.module.run):
			raise ModuleError(self.id, "module is not runnable")

		# Init inputs (via ContractWrapper)
		self.structure = ModuleStructure(Module)
		self.ports = OrderedDict({ arg.name: Port.from_structure(arg) for arg in self.structure.args })
		self.contract = ContractWrapper(Contract, self.id, self.ports, contract_config)

		# Init outputs (f/ future setting)
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
		port = str(res[0]) if type(res) is tuple and len(res) == 2 else 'default'
		value = res[1] if type(res) is tuple and len(res) == 2 else res

		dsts = [ dst for dst in self.dsts if dst.self_port == port ]
		if len(dsts) <= 0 and len(self.dsts) > 0:
			# TODO: log-level info when logging is up
			print(f"{self.id}: output port {port} has no destinations")

		for dst in dsts:
			key = (dst.other_node.id, dst.other_port)
			self.dst_counts[key] = self.dst_counts.get(key, -1) + 1
			payload = Payload(self.id, self.dst_counts[key], value)
			await dst.other_node.accept(val=payload, port=dst.other_port)

	async def run(self):
		inputs = {0} # Python has no do...while; dummy value to bootstrap loop
		while len(inputs) > 0: # Fancy method to ensure that nodes with no inputs only run once
			inputs = await self.contract.get_inputs()
			if isinstance(inputs, EndSentinel):
				break

			inputs = { name: i.payload for (name, i) in inputs.items() }

			res = None
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

		if self.dsts is None:
			raise ModuleError(self.id, "dsts have not been initialised")

		for dst in self.dsts:
			await dst.other_node.accept(val=EndSentinel(self.id), port=dst.other_port)
