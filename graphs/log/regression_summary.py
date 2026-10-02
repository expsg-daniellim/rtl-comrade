from __future__ import annotations
import sys
from pathlib import Path
from typing import Any
from collections.abc import MutableMapping
from serde import serde, field
from summary import SummaryAccumulator, build_events, FAIL_EVENTS, colourise

BUILDER_EVENT = "regression_builder"
BUILDER_MODE_EVENT = "regression_builder_mode"
SUITE_EVENT = "regression_suite"


class RegressionSummaryAccumulator(SummaryAccumulator):
	def __init__(self, events, suppress):
		super().__init__(events, suppress)
		self.builder = None
		self.mode = None
		self.suites = {}  # suite name → suite config path, in suite-event order

	def __call__(self, logger, method_name:str, event_dict:MutableMapping[str, Any]) -> MutableMapping[str, Any]:
		name = event_dict.get("event")
		if name == BUILDER_EVENT:
			self.builder = event_dict.get("builder")
		elif name == BUILDER_MODE_EVENT:
			self.mode = event_dict.get("mode")
		elif name == SUITE_EVENT:
			self.suites[event_dict.get("suite")] = event_dict.get("path")
		return super().__call__(logger, method_name, event_dict)

	def render_table(self) -> str|None:
		if len(self.rows) == 0:
			return None
		groups = { suite: [] for suite in self.suites }
		unmatched = []
		for row in self.rows:
			key = row["key"] or ""
			suite = key.split("/", 1)[0] if "/" in key else None
			(unmatched if suite is None else groups.get(suite, unmatched)).append(row)
		lines = ["\nRegression Results Summary", f"Builder: {self.builder or 'NA'}, Builder Mode: {self.mode or 'NA'}"]
		for suite, rows in groups.items():
			path = self.suites[suite]
			lines.extend( render_row("NA" if path is None else str(path), row) for row in rows )
		lines.extend( render_row("NA", row) for row in unmatched )
		n_fail = sum(1 for r in self.rows if r["result"] == "FAIL")
		if n_fail > 0:
			lines.append(f"\n{n_fail} failure{'s' if n_fail != 1 else ''}")
		return "\n".join(lines)


def render_row(suite_path:str, row:dict[str, Any]) -> str:
	return f"{suite_path:<35} {row['test_name'] or 'NA':<30} {row['result'] or 'NA':<8} {str(row['desc'] or 'NA')[:50]}"


class ConsoleRegressionSummaryProcessor(RegressionSummaryAccumulator):
	@serde
	class Config:
		fail:list[str] = field(default_factory=lambda: list(FAIL_EVENTS))
		pass_:list[str] = field(rename='pass', default_factory=lambda: ["parse_log_passed", "parse_uvm_passed"])
		skip:list[str] = field(default_factory=lambda: ["test_skipped"])
		na:list[str] = field(default_factory=lambda: ["test_stopped_early", "parse_log_unknown"])
		suppress:list[str] = field(default_factory=list)

	def __init__(self, config):
		super().__init__(build_events(config), config.suppress)

	def finalise(self):
		table = self.render_table()
		if table is None:
			return
		print(colourise(table) if sys.stdout.isatty() else table)


class FileRegressionSummaryProcessor(RegressionSummaryAccumulator):
	@serde
	class Config:
		fail:list[str] = field(default_factory=lambda: list(FAIL_EVENTS))
		pass_:list[str] = field(rename='pass', default_factory=lambda: ["parse_log_passed", "parse_uvm_passed"])
		skip:list[str] = field(default_factory=lambda: ["test_skipped"])
		na:list[str] = field(default_factory=lambda: ["test_stopped_early", "parse_log_unknown"])
		suppress:list[str] = field(default_factory=list)
		out:Path = field(default=Path("summary.log"))

	def __init__(self, config):
		super().__init__(build_events(config), config.suppress)
		self.out = config.out

	def finalise(self):
		table = self.render_table()
		if table is None:
			return
		try:
			with open(self.out, "w", encoding="utf-8") as f:
				f.write(table + "\n")
		except OSError:
			pass
