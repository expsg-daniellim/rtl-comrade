import inspect
from inspect import signature
from serde import serde, from_dict
import typing

from .port import Payload, EndSentinel, Port, ContractPort

class ContractError(BaseException):
	pass

class ContractWrapper:
	# Assume that ports has been validated and canonicalised
	def __init__(self, Contract, id:str, ports:dict[str, Port], config:dict):
		self.id = id
		# TODO: warn about config acceptance
		init_sig = signature(Contract.__init__)

		missing_params = [ param for param in ['id', 'ports'] if param not in init_sig.parameters ]
		if len(missing_params) > 0:
			raise ContractError(self.id, f"contract {Contract.__name__} does not have a valid init signature: {', '.join(missing_params)}")

		contract_ports = { name: ContractPort(get=port.get, try_get=port.try_get, has_default=port.has_default, default=port.default) for (name, port) in ports.items() }

		if 'config' in init_sig.parameters:
			if hasattr(Contract, 'Config'):
				config = from_dict(Contract.Config, config)
			self.contract = Contract(config=config, id=self.id, ports=contract_ports)
		else:
			self.contract = Contract(id=self.id, ports=contract_ports)

		if not hasattr(self.contract, 'get_inputs') or not inspect.isroutine(self.contract.get_inputs):
			raise ContractError(self.id, f"contract {Contract.__name__} is not runnable")

		self.ports = ports

	# Wrapper functions for get and get_nowait for now in case we want to add fancier stuff like observability
	async def get(self, port:str) -> Payload|EndSentinel:
		if not port in self.ports:
			raise AttributeError(f"{self.id}: unavailable port {port} requested")
		else:
			return await self.ports[port].queue.get()

	def try_get(self, port:str) -> Payload|EndSentinel|None:
		if not port in self.ports:
			raise AttributeError(f"{self.id}: unavailable port {port} requested")
		else:
			return self.ports[port].queue.get_nowait()

	async def get_inputs(self) -> dict[str, Payload|EndSentinel]:
		if inspect.iscoroutinefunction(self.contract.get_inputs):
			return await self.contract.get_inputs()
		else:
			return self.contract.get_inputs()
