from dataclasses import dataclass, field
import structlog

from rtl_comrade.api import Payload, EndSentinel, ContractPort

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
			# An ended port is a legitimate unselected branch arm only when it carries branch labels and no co-fated port (same labels) delivered; an unbranched port ending without data is a genuinely missing required input.
			delivered_labels = {port.branch_labels for name, port in self.ports.items() if name in inputs}
			conflicted = [name for name in missing if len(self.ports[name].branch_labels) == 0 or self.ports[name].branch_labels in delivered_labels]
			if conflicted:
				log.error("missing_required_inputs", contract=self.id, ports=conflicted)
			return EndSentinel(self.id)

		self._invoked = True
		return inputs
