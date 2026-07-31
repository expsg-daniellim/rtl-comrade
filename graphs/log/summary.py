from __future__ import annotations
import re
import sys
from pathlib import Path
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


FAIL_EVENTS = [
	"compile_failed", "sim_timeout",
	"preproc_script_not_found", "preproc_script_permission", "preproc_script_read_error", "preproc_script_error",
	"filelist_dir_not_found", "filelist_is_directory", "filelist_permission_denied", "filelist_write_error",
	"replay_seed_not_found", "replay_seed_malformed", "replay_seed_permission",
	"model_file_not_found", "model_is_directory", "model_permission_denied", "model_invalid_unicode", "model_parse_error", "model_not_found", "model_read_error",
	"sweep_script_not_found", "sweep_script_permission", "sweep_script_read_error", "sweep_script_error", "sweep_output_invalid",
	"parse_log_failed", "parse_log_unreadable",
	"parse_uvm_no_summary", "parse_uvm_invalid_summary", "parse_uvm_failed", "parse_uvm_unreadable",
]

DESC_BUILDERS = {
	"compile_failed": lambda e: "Compile failed",
	"sim_timeout": lambda e: "Sim hit timeout",
	"preproc_script_not_found": lambda e: f"preproc script not found: {e.get('preproc_path')}",
	"preproc_script_permission": lambda e: f"cannot read preproc script {e.get('preproc_path')}",
	"preproc_script_read_error": lambda e: f"cannot read preproc script {e.get('preproc_path')}",
	"preproc_script_error": lambda e: f"preproc script raised: {e.get('exc_info', '')}",
	"filelist_dir_not_found": lambda e: f"output directory missing for {e.get('path')}",
	"filelist_is_directory": lambda e: f"{e.get('path')} is a directory",
	"filelist_permission_denied": lambda e: f"cannot write {e.get('path')}",
	"filelist_write_error": lambda e: f"cannot write {e.get('path')}",
	"replay_seed_not_found": lambda e: f"Replay seed missing or invalid at {e.get('path')}",
	"replay_seed_malformed": lambda e: f"Replay seed missing or invalid at {e.get('path')}",
	"replay_seed_permission": lambda e: f"Replay seed missing or invalid at {e.get('path')}",
	"model_file_not_found": lambda e: f"models.yaml not found: {e.get('model_path')}",
	"model_is_directory": lambda e: f"{e.get('model_path')} is a directory",
	"model_permission_denied": lambda e: f"cannot read {e.get('model_path')}",
	"model_invalid_unicode": lambda e: f"{e.get('model_path')} is not valid UTF-8",
	"model_parse_error": lambda e: f"malformed {e.get('model_path')}: {e.get('err')}",
	"model_not_found": lambda e: f"model {e.get('model')!r} not in {e.get('model_path')}",
	"model_read_error": lambda e: f"cannot read {e.get('model_path')}",
	"sweep_script_not_found": lambda e: f"sweep script not found: {e.get('sweep_path')}",
	"sweep_script_permission": lambda e: f"cannot read sweep script {e.get('sweep_path')}",
	"sweep_script_read_error": lambda e: f"cannot read sweep script {e.get('sweep_path')}",
	"sweep_script_error": lambda e: f"sweep script raised: {e.get('exc_info', '')}",
	"sweep_output_invalid": lambda e: f"sweep script produced malformed out_test_cfgs: {e.get('err')}",
	"parse_log_failed": lambda e: e.get("desc"),
	"parse_log_unknown": lambda e: e.get("desc", "test result unknown"),
	"parse_log_unreadable": lambda e: e.get("desc"),
	"parse_uvm_no_summary": lambda e: e.get("desc"),
	"parse_uvm_invalid_summary": lambda e: e.get("desc"),
	"parse_uvm_failed": lambda e: e.get("desc"),
	"parse_uvm_unreadable": lambda e: e.get("desc"),
	"parse_log_passed": lambda e: e.get("desc"),
	"parse_uvm_passed": lambda e: e.get("desc"),
	"test_skipped": lambda e: e.get("reason"),
	"test_stopped_early": lambda e: f"Stopped early at {e.get('phase')}",
}


class SummaryAccumulator:
	def __init__(self, events, suppress):
		self.events = events  # dict: event_name → "FAIL"/"PASS"/"SKIP"/"NA"
		self.suppress = set(suppress)
		self.rows = []

	def __call__(self, logger, method_name:str, event_dict:MutableMapping[str, Any]) -> MutableMapping[str, Any]:
		name = event_dict.get("event")
		result = self.events.get(name)
		if result is not None:
			desc = DESC_BUILDERS.get(name, lambda e: None)(event_dict)
			self.rows.append({"test_name": event_dict.get("test_name"), "key": event_dict.get("key"), "result": result, "desc": desc})
			if name in self.suppress:
				raise DropEvent
		return event_dict

	def render_table(self) -> str | None:
		if len(self.rows) == 0:
			return None
		lines = ["\nTest Results Summary"]
		for row in self.rows:
			lines.append(f"{row['test_name'] or 'NA':<30} {row['result'] or 'NA':<8} {row['desc'] or 'NA':<30}")
		n_fail = sum(1 for r in self.rows if r["result"] == "FAIL")
		if n_fail > 0:
			lines.append(f"\n{n_fail} failure{'s' if n_fail != 1 else ''}")
		return "\n".join(lines)


def build_events(config) -> dict[str, str]:
	events = {}
	for name in config.fail:
		events[name] = "FAIL"
	for name in config.pass_:
		events[name] = "PASS"
	for name in config.skip:
		events[name] = "SKIP"
	for name in config.na:
		events[name] = "NA"
	return events


class ConsoleSummaryProcessor(SummaryAccumulator):
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


class FileSummaryProcessor(SummaryAccumulator):
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
