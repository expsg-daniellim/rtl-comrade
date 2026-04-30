from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from typing import Any
from serde import serde, field

from .api import Payload, EndSentinel, ContractPort

def is_special(port):
	return (port.persistent and port.last_value is not None) or port.has_default

@dataclass
class DefaultContract:
	id: str
	ports: dict[str, ContractPort]

	@serde
	class Config:
		persistent_inputs: list[str] = field(default_factory=list)

	def __init__(self, id:str, config:Config, ports:dict[str, ContractPort]):
		unknown_ports = [ i for i in config.persistent_inputs if not i in ports ]
		if len(unknown_ports) > 0:
			raise ValueError(f"{id}: unknown persistent ports: {', '.join(unknown_ports)}")

		self.id = id
		for port in ports.values():
			port.persistent = False
			port.last_value = None

		for port in config.persistent_inputs:
			ports[port].persistent = True

		self.ports = ports

	async def get_inputs(self) -> dict[str, Payload]|EndSentinel:
		# Order of precedence: required (non-special)/persistent (first run) > persistent (cached) > persistent (default) > default
		# Get required inputs
		inputs = {}
		for (name, port) in filter(lambda p: not is_special(p[1]), self.ports.items()):
			val = await port.get()
			if not isinstance(val, EndSentinel):
				port.last_value = val
			inputs[name] = val

		# Evaluate end sentinels of required ports first
		if any(isinstance(i, EndSentinel) for i in inputs.values()):
			if not all(isinstance(i, EndSentinel) for i in inputs.values()):
				raise ValueError("mismatched end of inputs")
			return EndSentinel(self.id)

		# Get special inputs
		special_inputs = {}
		for (name, port) in filter(lambda p: is_special(p[1]) and not p[0] in inputs, self.ports.items()):
			val = port.try_get()
			
			if not isinstance(val, EndSentinel) and val is not None:
				port.last_value = val
				special_inputs[name] = val
			elif port.persistent:
				if port.last_value is not None:
					special_inputs[name] = port.last_value
				elif port.has_default:
					default = port.get_default_payload()
					port.last_value = default
					special_inputs[name] = default
				else:
					raise ValueError(f"{self.id}: persistent port {name} has no last value")
			elif port.has_default and not port.has_ended():
				special_inputs[name] = port.get_default_payload()
			else:
				raise Exception(f"{self.id}: unsupported special case")
		# Special inputs should never have an EndSentinel, so no checking is done

		return inputs | special_inputs
