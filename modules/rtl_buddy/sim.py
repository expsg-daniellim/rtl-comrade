import dataclasses
import os
import random
import re
from pathlib import Path
from typing import cast

import structlog

from rtl_comrade.logging import HarnessLogger

from modules.rtl_buddy.schema import KeyedValue, SeedMode, TestResult, RtlBuilderConfig, Command, Proc, RandSeed, RandSeedDone
from modules.rtl_buddy.schema.suite import TestConfig

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())


class ExpandRunsMod:
	def run(self, test:TestConfig, simv:KeyedValue[str], run_ids:list = [None]):  # pylint: disable=dangerous-default-value  # read-only; [None] is the harness-visible default (structure.py reads it)
		for run_id in run_ids:
			nk = test.key if run_id is None else f"{test.key}#{run_id}"
			yield ("test", dataclasses.replace(test, key=nk))
			yield ("run_id", KeyedValue(nk, run_id))
			yield ("simv", KeyedValue(nk, simv.value))


def run_suffix(run_id) -> str:
	return "" if run_id is None else f"_{run_id:04d}"  # run-id zero-padded to four digits


class ResolveSeedMod:
	def run(self, test:TestConfig, run_id:int | None, simv:str, seed_mode:SeedMode, builder_cfg:RtlBuilderConfig, logs_dir:Path):
		if seed_mode == SeedMode.NEW:
			seed = random.randrange(1_000_000)
		elif seed_mode == SeedMode.DEFAULT:
			seed = builder_cfg.get_seed()
		else:  # REPLAY
			path = logs_dir / f"{test.get_name()}{run_suffix(run_id)}.randseed"
			try:
				with Path(path).open(encoding="utf-8") as f:
					seed = int(f.readline().strip())
			except FileNotFoundError:
				log.error("replay_seed_not_found", key=test.key, test_name=test.get_name(), path=str(path))
				yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}"))
				return
			except ValueError as e:
				log.error("replay_seed_malformed", key=test.key, test_name=test.get_name(), path=str(path), err=str(e))
				yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}"))
				return
			except PermissionError as e:
				log.error("replay_seed_permission", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror)
				yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}"))
				return
		yield ("test", test)
		yield ("run_id", run_id)
		yield ("simv", simv)
		yield ("seed", seed)


class BuildSimCmdMod:
	def run(self, test:TestConfig, run_id:int | None, simv:str, seed:int, builder_cfg:RtlBuilderConfig, builder_mode:str, logs_dir:Path):
		plusdefines = []
		pd = test.get_plusdefines()
		if pd is not None:
			for k, v in pd.items():
				plusdefines.append(f"+define+{k}={v}" if v is not None else f"+define+{k}")
		plusargs = []
		pa = test.get_plusargs()
		if pa is not None:
			for k, v in pa.items():
				plusargs.append(f"+{k}={v}" if v is not None else f"+{k}")
		argv = [simv, *builder_cfg.get_run_time_opts(builder_mode, seed=seed), *plusdefines, *plusargs]
		timeout, is_custom = test.get_timeout()
		if is_custom:
			log.warning("custom_sim_timeout", key=test.key, timeout=timeout)
		stem = logs_dir / f"{test.get_name()}{run_suffix(run_id)}"
		log_path, err_path, rs_path = f"{stem}.log", f"{stem}.err", f"{stem}.randseed"
		yield ("test", test)
		yield ("command", Command(test.key, argv=argv, stdout_path=log_path, stderr_path=err_path))
		yield ("timeout", float(timeout))
		yield ("randseed", RandSeed(test.key, seed=seed, randseed_path=rs_path, argv=argv))


class WriteRandseedMod:
	def run(self, randseed:RandSeed, proc:Proc, work_dir:Path):  # proc joined as a completion gate (rc unread); work_dir persistent
		try:
			Path(randseed.randseed_path).write_text(f"{randseed.seed}\n")
			if "hier_inst_seed" in randseed.argv:  # rtl_buddy membership check against the sim argv
				with open(Path(work_dir) / "HierInstanceSeed.txt", encoding="utf-8") as f, Path(randseed.randseed_path).open("a", encoding="utf-8") as out:
					out.writelines(f)  # read from work_dir (where the sim dropped it), not ambient CWD (rtl_buddy vlog_sim.py:263-269 parity)
		except OSError as e:  # FileNotFoundError (missing HierInstanceSeed.txt) is an OSError subclass
			log.error("randseed_write_failed", key=randseed.key, path=randseed.randseed_path, exc_info=e)
		return ("randseed_done", RandSeedDone(randseed.key))  # ordering signal emitted regardless, so link-latest can't dangle


def force_symlink(target, link_name) -> None:
	tmp = f"{link_name}.{os.getpid()}.tmp"
	os.symlink(target, tmp)
	os.replace(tmp, link_name)  # atomic rename over any existing link (or absent target)


class LinkLatestMod:
	def run(self, randseed: RandSeed, proc: Proc, randseed_done: RandSeedDone, work_dir: Path):  # randseed_done: ordering gate (after write-randseed); unread. work_dir persistent
		force_symlink(proc.stdout_path, Path(work_dir) / "test.log")
		force_symlink(proc.stderr_path, Path(work_dir) / "test.err")
		force_symlink(randseed.randseed_path, Path(work_dir) / "test.randseed")


class InterpretSimMod:
	def run(self, test:TestConfig, proc:Proc):
		if proc.rc is None:
			result = TestResult.sim_timeout(test.key, test.get_name())
			log.error("sim_timeout", key=test.key, err=proc.stderr_path)
			yield ("timeout", result)
		else:
			yield ("test", test)
			yield ("proc", proc)


class RoutePostMod:
	def run(self, test:TestConfig, proc:Proc):
		if test.uvm is not None:
			yield ("uvm_test", test)
			yield ("uvm_proc", proc)
		else:
			yield ("plain_test", test)
			yield ("plain_proc", proc)


class ParseLogMod:
	def run(self, test:TestConfig, proc:Proc):
		try:
			text = Path(proc.stdout_path).read_text(encoding="utf-8")
			match_pass = None
			match_fail = None
			match_err = None
			for line in text.splitlines():
				if match_pass is None:
					match_pass = re.match(r"PASS\b\s*(.*)", line)
				if match_fail is None:
					match_fail = re.match(r"FAIL\b\s*(.*)", line)
				if match_err is None:
					match_err = re.match(r"(ERR|FAT):\s*(.*)", line)
			if match_fail is not None:
				verdict = "FAIL"
				desc = f'{match_fail.group(1)} {match_err.group(2).strip()}' if match_err is not None else match_fail.group(1)
			elif match_pass is not None:
				verdict, desc = "PASS", match_pass.group(1)
			else:
				verdict, desc = "NA", "test result unknown"
			result = TestResult.parse(test.key, test.get_name(), verdict, desc)
			event = {"FAIL": "parse_log_failed", "NA": "parse_log_unknown"}.get(verdict)
		except OSError as e:
			result = TestResult.parse(test.key, test.get_name(), "FAIL", str(e))
			event = "parse_log_unreadable"
		if event is not None:
			log.error(event, key=test.key, test_name=test.get_name(), path=str(proc.stdout_path), desc=result.desc)
		return ("default", result)


class ParseUvmLogMod:
	def run(self, test:TestConfig, proc:Proc):
		uvm = test.uvm
		path = proc.stdout_path
		try:
			text = Path(path).read_text(encoding="utf-8")
			summary = re.search(
				r"-+\s*UVM Report Summary\s*-+\s*\**\s*Report counts by severity\s*((?:UVM_(?:INFO|WARNING|ERROR|FATAL)\s*:?\s*[0-9]+\s?)+)",
				text,
			)
			if summary is None:
				result = TestResult.parse(test.key, test.get_name(), "FAIL", f"No UVM Report Summary detected. See {path}.")
				event = "parse_uvm_no_summary"
			else:
				totals = dict(
					(m.group(1), int(m.group(2)))
					for m in re.finditer(r"^UVM_(INFO|WARNING|ERROR|FATAL)\s*:?\s*([0-9]+)", summary.group(1), re.MULTILINE)
				)
				if "WARNING" not in totals or "ERROR" not in totals or "FATAL" not in totals:
					result = TestResult.parse(test.key, test.get_name(), "FAIL", f"Invalid UVM Report Summary detected. See {path}")
					event = "parse_uvm_invalid_summary"
				else:
					message_summary = ", ".join(
						f"{v} uvm {k.lower()}{'s' if v != 1 else ''}"
						for k, v in totals.items() if k != "INFO"
					)
					results_str = f"{message_summary} detected. max_warnings={uvm.max_warns}, max_err={uvm.max_errors}"
					if totals["WARNING"] <= uvm.max_warns and totals["ERROR"] <= uvm.max_errors and totals["FATAL"] == 0:
						result = TestResult.parse(test.key, test.get_name(), "PASS", results_str)
						event = None
					else:
						result = TestResult.parse(test.key, test.get_name(), "FAIL", f"{results_str}. See {path}")
						event = "parse_uvm_failed"
		except OSError as e:
			result = TestResult.parse(test.key, test.get_name(), "FAIL", str(e))
			event = "parse_uvm_unreadable"
		if event is not None:
			log.error(event, key=test.key, test_name=test.get_name(), path=str(path), desc=result.desc)
		return ("default", result)
