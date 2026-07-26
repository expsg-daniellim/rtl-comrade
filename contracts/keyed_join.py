from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any, cast

import structlog

from rtl_comrade.api import Payload, EndSentinel, ContractPort
from rtl_comrade.logging import HarnessLogger

from contracts.sentinels import KeyedValue

log: HarnessLogger = cast(HarnessLogger, structlog.get_logger())

# A port may use its module default when it has one and the graph does not mark it required.
def can_default(port: ContractPort) -> bool:
	return port.has_default and not port.required

# The correlation key is a payload's ``key_field`` attribute when present, else its ``key_field`` dict entry.
def key_of(payload: Any, key_field: str) -> Any:
	return getattr(payload, key_field) if hasattr(payload, key_field) else payload[key_field]

# A payload is wrapper-shaped only when it carries a ``value`` alongside its key; anything else (a self-keyed record) passes through whole.
def unwrap_payload(val: Payload, key_field: str) -> Payload:
	inner = val.payload
	if hasattr(inner, key_field) and hasattr(inner, 'value'):
		return replace(val, payload=inner.value)
	if isinstance(inner, dict) and key_field in inner and 'value' in inner:
		return replace(val, payload=inner['value'])
	return val


@dataclass
class KeyedJoinContract:
	"""Invokes the module when all keyed ports have data for the same correlation key.

	Items from keyed ports are matched by a correlation key: a payload's ``key_field`` attribute
	when present, otherwise the ``key_field`` entry of a payload dict. ``key_field`` names the
	field in both cases and defaults to ``"key"``. Keys may arrive
	interleaved across ports; partial groups are buffered until complete. When all keyed
	ports have ended, a key held by only some co-fated ports (those sharing branch labels)
	within a partition is logged as an error; a key a whole partition never received is a
	branch legitimately not selected and is not flagged.

	Ports named in ``persistent_inputs`` are singletons replayed on every keyed assembly.
	A persistent input need not carry a key; when it does, its latest value is
	additionally cached per key, and a keyed assembly prefers the value cached for that key,
	falling back to the most-recent value. The first keyed assembly blocks until every
	persistent port that cannot fall back to a module default has delivered a value; a
	persistent port whose module parameter has a default (and is not marked required) never
	blocks, its key being omitted so the Python default applies until a real value arrives,
	mirroring ``DefaultContract``. A persistent port ending neither terminates the join nor
	participates in key completeness.

	Under ``unwrap`` the contract serves both ends: it hands the module the inner value of each
	wrapper-shaped payload and rewraps every emitted value in a ``KeyedValue`` carrying the
	assembled key, so the module never handles correlation keys itself. Output ports named in
	``ignore`` are left alone. Serving as a node's general ``contract`` always routes its outputs
	through ``process_outputs``; with ``unwrap`` off that is an exact pass-through.
	"""

	@dataclass(frozen=True)
	class Config:
		key_field:str = "key"
		persistent_inputs:list[str] = field(default_factory=list)
		unwrap:bool = False
		ignore:list[str] = field(default_factory=list)

	id: str
	ports: dict[str, ContractPort]
	current_key: Any

	def __init__(self, id: str, config: Config, ports: dict[str, ContractPort]):  # pylint: disable=redefined-builtin
		unknown_ports = [ name for name in config.persistent_inputs if name not in ports ]
		if len(unknown_ports) > 0:
			log.fatal('unknown_persistent_ports', context='harness.contract.init', port=unknown_ports)

		if len(config.ignore) > 0 and not config.unwrap:
			log.warn('ignore_without_unwrap', context='harness.contract.init', port=config.ignore)

		self.id = id
		self.config = config
		self.ports = ports
		self.current_key = None
		self.keyed = { name: port for name, port in ports.items() if name not in config.persistent_inputs }
		self.persistent = { name: port for name, port in ports.items() if name in config.persistent_inputs }
		self.buffers: dict[str, dict[Any, Payload]] = {}
		for port in self.persistent.values():
			port.state['last_value'] = None
			port.state['keyed'] = {}

	async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
		while True:
			for name, port in self.ports.items():
				if port.has_ended():
					continue
				while True:
					val = port.try_get()
					if val is None:
						break
					if isinstance(val, EndSentinel):
						self.on_end(name)
						break
					self.store(name, val)

			complete_key = self.find_complete_key()
			if complete_key is not None:
				if self.persistent_ready():
					result = {name: self.buffers[name].pop(complete_key) for name in self.keyed}
					for name, port in self.persistent.items():
						value = port.state['keyed'].get(complete_key, port.state['last_value'])
						if value is not None:
							result[name] = value
					if self.config.unwrap:
						result = { name: unwrap_payload(val, self.config.key_field) for name, val in result.items() }
					self.current_key = complete_key
					return result
				# Hold the complete group until every persistent input has delivered; a keyed
				# port ending does not cancel an already-complete group. Block on persistent.
				blocking = self.persistent
			else:
				if all(port.has_ended() for port in self.keyed.values()):
					incomplete = self.find_incomplete_keys()
					if len(incomplete) > 0:
						log.error("incomplete_keys", contract=self.id, keys=incomplete)
					self.current_key = None
					return EndSentinel(self.id)

				blocking = self.keyed

			# Block on a port whose arrival can unblock emission. Ports already holding a value,
			# ended, or able to fall back to their module default are skipped; keyed ports have no
			# 'last_value' and cannot default, so they are never skipped.
			for name, port in blocking.items():
				if port.has_ended() or port.state.get('last_value') is not None:
					continue
				if name in self.persistent and can_default(port):
					continue
				val = await port.get()
				if isinstance(val, EndSentinel):
					self.on_end(name)
				else:
					self.store(name, val)
				break

	def process_outputs(self, port:str, value:Any) -> Any:
		if not self.config.unwrap or port in self.config.ignore:
			return value

		# finalise() emits after the last assembly, so there is no key to attach and the value travels as the module made it.
		if self.current_key is None:
			log.warn('no_active_key', contract=self.id, port=port)
			return value

		return KeyedValue(self.current_key, value)

	def store(self, name: str, val: Payload) -> None:
		if name in self.persistent:
			port = self.persistent[name]
			port.state['last_value'] = val
			if hasattr(val.payload, self.config.key_field) or (isinstance(val.payload, dict) and self.config.key_field in val.payload):
				port.state['keyed'][key_of(val.payload, self.config.key_field)] = val
		else:
			key = key_of(val.payload, self.config.key_field)
			self.buffers.setdefault(name, {})[key] = val

	def on_end(self, name: str) -> None:
		if name in self.persistent and self.persistent[name].state['last_value'] is None and not can_default(self.persistent[name]):
			log.error("persistent_input_ended_without_value", contract=self.id, port=name)

	def find_complete_key(self) -> Any:
		all_keys: set[Any] = set()
		for name in self.keyed:
			all_keys |= set(self.buffers.get(name, {}).keys())
		complete = [k for k in all_keys if all(k in self.buffers.get(n, {}) for n in self.keyed)]
		return min(complete) if complete else None

	def find_incomplete_keys(self) -> list[Any]:
		partitions: dict[frozenset, list[str]] = defaultdict(list)
		for name, port in self.keyed.items():
			partitions[port.branch_labels].append(name)
		all_keys: set[Any] = set()
		for name in self.keyed:
			all_keys |= set(self.buffers.get(name, {}).keys())
		# A key is a desync only when a control-dependence partition holds it on some co-fated ports but not all; a whole partition missing the key is an arm legitimately not selected.
		return [k for k in all_keys if any(0 < sum(k in self.buffers.get(n, {}) for n in names) < len(names) for names in partitions.values())]

	def persistent_ready(self) -> bool:
		return all(port.state['last_value'] is not None or port.has_ended() or can_default(port) for port in self.persistent.values())
