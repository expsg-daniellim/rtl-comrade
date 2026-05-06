from dataclasses import dataclass
from rtl_comrade.api import Payload, EndSentinel, ContractPort
import structlog

log = structlog.get_logger()

@dataclass
class ZipContract:
	id: str
	ports: dict[str, ContractPort]

	async def get_inputs(self) -> dict[str, Payload]|EndSentinel:
		res = { name: await port.get() for (name, port) in self.ports.items() }
		if any(isinstance(val, EndSentinel) for val in res.values()):
			if not all(isinstance(val, EndSentinel) for val in res.values()):
				log.error('%s.mismatched_ends', self.id)
			return EndSentinel(self.id)

		return res
