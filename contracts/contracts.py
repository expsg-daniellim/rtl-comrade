from dataclasses import dataclass
from rtl_comrade.api import Payload, EndSentinel, ContractPort

@dataclass
class ZipContract:
	id: str
	ports: dict[str, ContractPort]

	async def get_inputs(self) -> dict[str, Payload]|EndSentinel:
		res = { name: await port.get() for (name, port) in self.ports }
		if any(isinstance(val, EndSentinel) for val in res.values()):
			if not all(isinstance(val, EndSentinel) for val in res.values()):
				raise AttributeError(f"{self.id}: mismatched end queues")
			return EndSentinel(self.id)

		return res
