from dataclasses import dataclass, field
from rtl_comrade.api import Payload, EndSentinel, ContractPort
import structlog

log = structlog.get_logger()


@dataclass
class UnitContract:
	"""Contract that reads exactly one item from each port and invokes the module once.

	Suitable for setup or config-style nodes that should run exactly once.
	Missing required inputs (EndSentinel before any data) and duplicate inputs
	(extra data after the one consumed item) are logged as errors.
	"""

	id: str
	ports: dict[str, ContractPort]
	_invoked: bool = field(default=False, init=False, repr=False)

	async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
		if self._invoked:
			duplicates = [name for name, port in self.ports.items() if isinstance(port.try_get(), Payload)]
			if duplicates:
				log.error("duplicate_inputs", contract=self.id, ports=duplicates)
			return EndSentinel(self.id)

		inputs = {}
		missing = []
		for name, port in self.ports.items():
			val = await port.get()
			if isinstance(val, EndSentinel):
				missing.append(name)
			else:
				inputs[name] = val

		if missing:
			log.error("missing_required_inputs", contract=self.id, ports=missing)
			return EndSentinel(self.id)

		self._invoked = True
		return inputs
