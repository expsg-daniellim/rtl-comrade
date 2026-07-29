from typing import cast

import structlog
from serde import serde

from rtl_comrade.logging import HarnessLogger

from modules.rtl_buddy.schema import RunDepth

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())


class EarlyStopGateMod:
	@serde
	class Config:
		phase: str  # "pre" | "comp" | "sim"

	def __init__(self, config):
		self.phase = config.phase

	def run(self, early_stop: str = "post", **edges):
		order = [d.value for d in RunDepth]
		if early_stop not in order:
			log.fatal("invalid_early_stop", early_stop=early_stop, valid=order)
		test = edges["test"]
		if order.index(early_stop) <= order.index(self.phase):
			log.info("test_stopped_early", key=test.key, test_name=test.get_name(), phase=self.phase)
		else:
			for name, payload in edges.items():
				yield (name, payload)
