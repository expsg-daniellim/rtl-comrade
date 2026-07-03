from __future__ import annotations
import re
import sys
from typing import Any
from collections.abc import MutableMapping
from serde import serde, field
from structlog.exceptions import DropEvent

VERDICT_COLOURS = {"PASS": "\033[1;92m", "FAIL": "\033[1;91m", "NA": "\033[1;93m"}  # SKIP left plain — rtl_buddy parity
COLOUR_END = "\033[0m"


def colourise(line:str) -> str:
	for tok, colour in VERDICT_COLOURS.items():
		line = re.sub(rf"\b{tok}\b", f"{colour}{tok}{COLOUR_END}", line)
	return line


class SummaryProcessor:
	@serde
	class Config:
		events:list[str] = field(default_factory=lambda: ["test_result"])
		suppress:list[str] = field(default_factory=lambda: ["test_result"])

	def __init__(self, config):
		self.events = set(config.events)
		self.suppress = set(config.suppress)
		self.rows = []  # fresh per run

	def __call__(self, logger, method_name:str, event_dict:MutableMapping[str, Any]) -> MutableMapping[str, Any]:
		name = event_dict.get("event")
		if name in self.events:
			self.rows.append({"test_name": event_dict.get("test_name"), "key": event_dict.get("key"), "result": event_dict.get("result"), "desc": event_dict.get("desc")})
			if name in self.suppress:
				raise DropEvent
		return event_dict

	def finalise(self):
		if not self.rows:
			return
		colour = sys.stdout.isatty()
		lines = ["\nTest Results Summary"]
		for row in self.rows:
			line = f"{row['test_name'] or 'NA':<30} {row['result'] or 'NA':<8} {row['desc'] or 'NA':<30}"
			lines.append(colourise(line) if colour else line)
		print("\n".join(lines))
