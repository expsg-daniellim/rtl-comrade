import asyncio
from dataclasses import dataclass, field
from typing import cast

import structlog

from rtl_comrade.api import Payload, EndSentinel, ContractPort
from rtl_comrade.logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())


@dataclass
class AnyContract:
	"""Fire on any single ready port; end when all ports end.

	Each delivery carries one ready port's value under its output port, resolved once into
	``port.state['output']``. ``config.mapping`` is either a single port name (n→1: the whole
	fan-in funnels onto it) or an output-port → input-ports map (m→n: every input port must
	be assigned a group, else a construction error).
	"""

	@dataclass(frozen=True)
	class Config:
		mapping:str | dict[str, list[str]] = "default"

	id:str
	ports:dict[str, ContractPort]
	config:Config = field(default_factory=Config)
	pending:dict[str, asyncio.Task] = field(default_factory=dict, init=False, repr=False)

	def __post_init__(self):
		if isinstance(self.config.mapping, str):
			for port in self.ports.values():
				port.state['output'] = self.config.mapping
			return
		for output, in_ports in self.config.mapping.items():
			for name in in_ports:
				if name not in self.ports:
					log.fatal('unknown_input_port', context='harness.contract.init', port=name)
				if 'output' in self.ports[name].state:
					log.fatal('ambiguous_output_mapping', context='harness.contract.init', port=name)
				self.ports[name].state['output'] = output
		for name, port in self.ports.items():
			if 'output' not in port.state:
				log.fatal('unmapped_input_port', context='harness.contract.init', port=name)

	async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
		for name, port in self.ports.items():
			if not port.has_ended() and name not in self.pending:
				self.pending[name] = asyncio.ensure_future(port.get())

		while self.pending:
			done, _ = await asyncio.wait(self.pending.values(), return_when=asyncio.FIRST_COMPLETED)
			for name, task in list(self.pending.items()):
				if task not in done:
					continue
				val = task.result()
				del self.pending[name]
				if isinstance(val, EndSentinel):
					continue
				return {self.ports[name].state['output']: val}

		return EndSentinel(self.id)
