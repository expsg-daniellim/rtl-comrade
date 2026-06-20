from dataclasses import dataclass, field
from typing import Any, cast

import structlog

from rtl_comrade.api import Payload, EndSentinel, ContractPort
from rtl_comrade.logging import HarnessLogger

log: HarnessLogger = cast(HarnessLogger, structlog.get_logger())

# A port may use its module default when it has one and the graph does not mark it required.
def _can_default(port: ContractPort) -> bool:
	return port.has_default and not port.required


@dataclass
class KeyedJoinContract:
	"""Invokes the module when all keyed ports have data for the same correlation key.

	Items from keyed ports are matched by a field in their payload dict (``key_field``).
	Keys may arrive interleaved across ports; partial groups are buffered until complete.
	When any keyed port ends with buffered incomplete keys, those keys are logged as an error.

	Ports named in ``persistent_inputs`` are singletons replayed on every keyed assembly.
	A persistent input need not carry ``key_field``; when it does, its latest value is
	additionally cached per key, and a keyed assembly prefers the value cached for that key,
	falling back to the most-recent value. The first keyed assembly blocks until every
	persistent port that cannot fall back to a module default has delivered a value; a
	persistent port whose module parameter has a default (and is not marked required) never
	blocks, its key being omitted so the Python default applies until a real value arrives,
	mirroring ``DefaultContract``. A persistent port ending neither terminates the join nor
	participates in key completeness.
	"""

	@dataclass(frozen=True)
	class Config:
		key_field: str
		persistent_inputs: list[str] = field(default_factory=list)

	id: str
	ports: dict[str, ContractPort]

	def __init__(self, id: str, config: Config, ports: dict[str, ContractPort]):  # pylint: disable=redefined-builtin
		unknown_ports = [ name for name in config.persistent_inputs if name not in ports ]
		if len(unknown_ports) > 0:
			log.fatal('unknown_persistent_ports', context='harness.contract.init', port=unknown_ports)

		self.id = id
		self.config = config
		self.ports = ports
		self._keyed = { name: port for name, port in ports.items() if name not in config.persistent_inputs }
		self._persistent = { name: port for name, port in ports.items() if name in config.persistent_inputs }
		self._buffers: dict[str, dict[Any, Payload]] = {}
		for port in self._persistent.values():
			port.state['last_value'] = None
			port.state['keyed'] = {}

	async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
		saw_end: list[str] = []

		while True:
			for name, port in self.ports.items():
				if port.has_ended():
					continue
				while True:
					val = port.try_get()
					if val is None:
						break
					if isinstance(val, EndSentinel):
						self._on_end(name, saw_end)
						break
					self._store(name, val)

			complete_key = self._find_complete_key()
			if complete_key is not None:
				if self._persistent_ready():
					result = {name: self._buffers[name].pop(complete_key) for name in self._keyed}
					for name, port in self._persistent.items():
						value = port.state['keyed'].get(complete_key, port.state['last_value'])
						if value is not None:
							result[name] = value
					return result
				# Hold the complete group until every persistent input has delivered; a keyed
				# port ending does not cancel an already-complete group. Block on persistent.
				blocking = self._persistent
			else:
				if saw_end:
					incomplete = self._find_incomplete_keys()
					if incomplete:
						log.error("incomplete_keys", contract=self.id, keys=incomplete)
					return EndSentinel(self.id)

				if all(port.has_ended() for port in self._keyed.values()):
					return EndSentinel(self.id)

				blocking = self._keyed

			# Block on a port whose arrival can unblock emission. Ports already holding a value,
			# ended, or able to fall back to their module default are skipped; keyed ports have no
			# 'last_value' and cannot default, so they are never skipped.
			for name, port in blocking.items():
				if port.has_ended() or port.state.get('last_value') is not None:
					continue
				if name in self._persistent and _can_default(port):
					continue
				val = await port.get()
				if isinstance(val, EndSentinel):
					self._on_end(name, saw_end)
				else:
					self._store(name, val)
				break

	def _store(self, name: str, val: Payload) -> None:
		if name in self._persistent:
			port = self._persistent[name]
			port.state['last_value'] = val
			if isinstance(val.payload, dict) and self.config.key_field in val.payload:
				port.state['keyed'][val.payload[self.config.key_field]] = val
		else:
			key = val.payload[self.config.key_field]
			self._buffers.setdefault(name, {})[key] = val

	def _on_end(self, name: str, saw_end: list[str]) -> None:
		if name in self._keyed:
			saw_end.append(name)  # keyed endings drive termination
		elif self._persistent[name].state['last_value'] is None and not _can_default(self._persistent[name]):
			log.error("persistent_input_ended_without_value", contract=self.id, port=name)

	def _find_complete_key(self) -> Any:
		all_keys: set[Any] = set()
		for name in self._keyed:
			all_keys |= set(self._buffers.get(name, {}).keys())
		complete = [k for k in all_keys if all(k in self._buffers.get(n, {}) for n in self._keyed)]
		return min(complete) if complete else None

	def _find_incomplete_keys(self) -> list[Any]:
		all_keys: set[Any] = set()
		for name in self._keyed:
			all_keys |= set(self._buffers.get(name, {}).keys())
		return [k for k in all_keys if not all(k in self._buffers.get(n, {}) for n in self._keyed)]

	def _persistent_ready(self) -> bool:
		return all(port.state['last_value'] is not None or port.has_ended() or _can_default(port) for port in self._persistent.values())
