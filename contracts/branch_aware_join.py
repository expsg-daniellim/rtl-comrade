from dataclasses import dataclass
from typing import Any

import structlog

from rtl_comrade.api import Payload, EndSentinel, ContractPort

log = structlog.get_logger()

# The correlation key is a payload's key_field attribute when present, else its key_field dict entry.
def key_of(payload: Any, key_field: str) -> Any:
	return getattr(payload, key_field) if hasattr(payload, key_field) else payload[key_field]


@dataclass
class BranchAwareJoinContract:
	"""Joins inputs by key, using branch_labels to exclude ports whose arm was not selected.

	Two ports that are alternative arms of the same origin (equal origin id in their
	branch_labels, differing arm) are mutually exclusive per key: an origin selects one
	arm per key. When a key arrives on one arm, its co-arm siblings are excluded from that
	key's assembly, so the join emits without them and their module parameters fall back to
	their Python defaults. A port with no branch labels is an unconditional participant,
	awaited until it delivers the key or ends. A port that ends is excluded from any key it
	has not delivered. The join therefore fires each key with whichever ports participated,
	and terminates only once every port has ended.
	"""

	@dataclass(frozen=True)
	class Config:
		key_field: str

	id: str
	ports: dict[str, ContractPort]

	def __init__(self, id: str, config: Config, ports: dict[str, ContractPort]):  # pylint: disable=redefined-builtin
		self.id = id
		self.config = config
		self.ports = ports
		self.buffers: dict[str, dict[Any, Payload]] = {}
		# origin id -> port name -> the arm that port depends on under that origin
		self.origin_arms: dict[Any, dict[str, frozenset]] = {}
		for name, port in ports.items():
			for (origin, arm) in port.branch_labels:
				self.origin_arms.setdefault(origin, {})[name] = arm

	async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
		while True:
			for name, port in self.ports.items():
				if port.has_ended():
					continue
				while True:
					val = port.try_get()
					if val is None or isinstance(val, EndSentinel):
						break
					self.buffers.setdefault(name, {})[key_of(val.payload, self.config.key_field)] = val

			complete_key = self.find_complete_key()
			if complete_key is not None:
				self.check_desync(complete_key)
				return {name: self.buffers[name].pop(complete_key) for name in self.ports if complete_key in self.buffers.get(name, {})}

			if all(port.has_ended() for port in self.ports.values()):
				return EndSentinel(self.id)

			for name, port in self.ports.items():
				if not port.has_ended():
					val = await port.get()
					if not isinstance(val, EndSentinel):
						self.buffers.setdefault(name, {})[key_of(val.payload, self.config.key_field)] = val
					break

	# A key is complete once every port is present, ended, or excluded by a selected co-arm sibling.
	def find_complete_key(self) -> Any:
		all_keys: set[Any] = set()
		for name in self.ports:
			all_keys |= set(self.buffers.get(name, {}).keys())
		complete = [ k for k in all_keys if all(k in self.buffers.get(name, {}) or self.ports[name].has_ended() or self.is_excluded(name, k) for name in self.ports) ]
		return min(complete) if complete else None

	# A port is excluded for a key when, under some origin gating it, a sibling arm has delivered that key.
	def is_excluded(self, name: str, key: Any) -> bool:
		for arms in self.origin_arms.values():
			if name not in arms:
				continue
			for other, other_arm in arms.items():
				if other_arm != arms[name] and key in self.buffers.get(other, {}):
					return True
		return False

	# Two co-arm siblings holding the same key means one origin selected two arms for it — a key-hygiene violation.
	def check_desync(self, key: Any) -> None:
		for origin, arms in self.origin_arms.items():
			present_arms = { arm for name, arm in arms.items() if key in self.buffers.get(name, {}) }
			if len(present_arms) > 1:
				log.error("conflicting_arms", contract=self.id, origin=origin, key=key)
