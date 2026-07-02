import re
from dataclasses import dataclass
from typing import cast

import structlog
from serde import serde, field

from rtl_comrade.logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

def process_opts(opts):
	return re.sub(r'\s+', ' ', opts).strip().split(' ')


@serde
@dataclass
class RtlBuilderConfigOpts:
	compile_time:list[str] | None = field(rename='compile-time', deserializer=process_opts)
	run_time:list[str] | None = field(rename='run-time', deserializer=process_opts)


@serde
@dataclass
class RtlBuilderConfig:
	name:str
	exe:str = field(rename='builder')
	simv:str = field(rename='builder-simv')
	sim_rand_seed:int = field(rename='sim-rand-seed')
	sim_rand_prefix:str = field(rename='sim-rand-seed-prefix')
	opts:dict[str, RtlBuilderConfigOpts] = field(rename='builder-opts')

	def get_name(self) -> str:
		return self.name

	def get_exe(self) -> str:
		return self.exe

	def get_simv(self) -> str:
		return self.simv

	def get_seed(self) -> int:
		return self.sim_rand_seed

	def get_modes(self) -> list[str]:
		return list(self.opts.keys())

	def get_compile_time_opts(self, mode:str) -> list[str]:
		if mode not in self.opts:
			log.fatal("builder_mode_missing", mode=mode)
		if self.opts[mode].compile_time is None:
			log.fatal("compile_time_opts_missing", mode=mode)
		return list(self.opts[mode].compile_time)

	def get_run_time_opts(self, mode:str, seed:int | None = None) -> list[str]:
		if mode not in self.opts:
			log.fatal("builder_mode_missing", mode=mode)
		if self.opts[mode].run_time is None:
			log.fatal("run_time_opts_missing", mode=mode)
		opts = list(self.opts[mode].run_time)
		if seed is not None:
			opts.append(self.sim_rand_prefix + str(seed))
		return opts
