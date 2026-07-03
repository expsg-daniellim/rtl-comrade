from collections import defaultdict
from dataclasses import dataclass
import structlog

from rtl_comrade.api import Payload, EndSentinel, ContractPort

log = structlog.get_logger()


@dataclass
class ZipContract:
	id: str
	ports: dict[str, ContractPort]

	async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
		res = {name: await port.get() for (name, port) in self.ports.items()}
		if any(isinstance(val, EndSentinel) for val in res.values()):
			# A branch may end one arm while another stays live, so a data/end split is only a mismatch within a single control-dependence partition (ports sharing branch labels).
			ended: dict[frozenset, set[str]] = defaultdict(set)
			live: dict[frozenset, set[str]] = defaultdict(set)
			for name, val in res.items():
				(ended if isinstance(val, EndSentinel) else live)[self.ports[name].branch_labels].add(name)
			conflicted = ended.keys() & live.keys()
			if len(conflicted) > 0:
				log.error("mismatched_ends", contract=self.id, has_data=sorted(n for labels in conflicted for n in live[labels]), has_end_sentinels=sorted(n for labels in conflicted for n in ended[labels]))
			return EndSentinel(self.id)

		# Above filter should have gotten rid of EndSentinel in return
		return res  # ty: ignore[invalid-return-type]
