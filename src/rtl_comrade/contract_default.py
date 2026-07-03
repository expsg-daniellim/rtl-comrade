"""Built-in default scheduling contract for runtime nodes."""

from collections import defaultdict
from dataclasses import dataclass
from typing import cast

from serde import serde, field
import structlog

from .api import Payload, EndSentinel, ContractPort
from .logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

# A special port is either default or a persistent port not on its first run.
def is_special(port:ContractPort) -> bool:
	"""Return whether a port is eligible to be satisfied without blocking.

	A port is special when it has a default value, or when it is persistent and
	already has a cached last value. Special ports may still consume a queued
	real payload via try_get() before falling back to cached/default behavior.

	A required port is never special: it is always awaited, even when it has a
	default value, so has_default is ignored for required ports.

	Args:
		port: Contract-owned port object carrying default/persistent state.

	Returns:
		``True`` if the port is currently special, otherwise ``False``.
	"""

	return (port.state['persistent'] and port.state['last_value'] is not None) or (port.has_default and not port.required)

@dataclass
class DefaultContract:
	"""Default contract providing basic required/default/persistent input handling.

	Attributes:
		id: Runtime id of the contract instance.
		ports: Contract-facing port adapters used to gather one invocation's inputs.
	"""

	id: str
	ports: dict[str, ContractPort]

	@serde
	class Config:
		"""Configuration for the built-in default contract.

		Attributes:
			persistent_inputs: Input-port names whose latest values should be reused
				across later invocations.
		"""

		persistent_inputs: list[str] = field(default_factory=list)

	def __init__(self, id:str, config:Config, ports:dict[str, ContractPort]):  # pylint: disable=redefined-builtin
		"""Configure persistent-input behavior for this contract instance.

		Args:
			id: Runtime id of the contract instance.
			config: Parsed default-contract configuration.
			ports: Contract-facing port adapters available to this contract.

		Returns:
			None.
		"""

		unknown_ports = [ input_ for input_ in config.persistent_inputs if input_ not in ports ]
		if len(unknown_ports) > 0:
			log.fatal('unknown_persistent_ports', context='harness.contract.init', port=unknown_ports)

		self.id = id
		for port in ports.values():
			port.state['persistent'] = False
			port.state['last_value'] = None

		for port_name in config.persistent_inputs:
			ports[port_name].state['persistent'] = True

		self.ports = ports

	async def get_inputs(self) -> dict[str, Payload]|EndSentinel:
		"""Assemble the next module invocation according to default-contract rules.

		Precedence is:
		1. required non-special inputs, including persistent inputs on first run
		2. queued updates for special inputs via non-blocking reads
		3. cached persistent values
		4. default-valued ports with nothing queued — key omitted; the module's default value applies

		Returns:
			A mapping from input-port name to Payload for the next invocation, or an
			EndSentinel when the node should terminate. Default-valued ports with no
			queued payload are absent from the dict.
		"""

		# Order of precedence: required > queued special > persistent cached > omit (default)
		# Get required inputs
		inputs = {}
		for (name, port) in filter(lambda p: not is_special(p[1]), self.ports.items()):
			val = await port.get()
			if not isinstance(val, EndSentinel):
				port.state['last_value'] = val
			inputs[name] = val

		# A branch may legitimately end one arm while another stays live, so a data/end split is only a
		# mismatch within a single control-dependence partition (ports sharing the same branch labels).
		ended:dict[frozenset, set[str]] = defaultdict(set)
		live:dict[frozenset, set[str]] = defaultdict(set)
		for (name, i) in inputs.items():
			(ended if isinstance(i, EndSentinel) else live)[self.ports[name].branch_labels].add(name)

		if len(ended) > 0:
			conflicted = ended.keys() & live.keys() # partitions holding both an ended and a live port
			if len(conflicted) > 0:
				log.error('mismatched_end', has_data=sorted(n for labels in conflicted for n in live[labels]), has_end_sentinels=sorted(n for labels in conflicted for n in ended[labels]))
			return EndSentinel(self.id)

		# Get special inputs
		special_inputs = {}
		for (name, port) in filter(lambda p: is_special(p[1]) and p[0] not in inputs, self.ports.items()):
			val = port.try_get()

			if not isinstance(val, EndSentinel) and val is not None:
				port.state['last_value'] = val
				special_inputs[name] = val
			elif port.state['persistent'] and port.state['last_value'] is not None:
				special_inputs[name] = port.state['last_value']
			# otherwise the key is omitted; Python's default activates for this port
		# Special inputs should never have an EndSentinel, so no checking is done

		return inputs | special_inputs
