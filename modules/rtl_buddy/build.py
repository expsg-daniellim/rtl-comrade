import asyncio
import os
import re
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import structlog
from serde import serde

from rtl_comrade.logging import HarnessLogger

from modules.rtl_buddy.schema import RootConfig, ModelConfig, Command, Proc, RtlBuilderConfig
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())


class RunPreprocMod:
	def run(self, test:TestConfig, model:ModelConfig, root_cfg:RootConfig):
		preproc = test.get_preproc_path()
		if preproc is None:
			yield ("test", test)
			yield ("model", model)
			return

		name = test.model
		ns = {"logger": log, "test_cfg": test, "root_cfg": root_cfg}
		try:
			with open(preproc, encoding="utf-8") as f:
				code = f.read()
		except FileNotFoundError:
			log.error("preproc_script_not_found", key=test.key, test_name=test.get_name(), preproc_path=str(preproc))
			return
		except PermissionError as e:
			log.error("preproc_script_permission", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), err=e.strerror)
			return
		except OSError as e:
			log.error("preproc_script_read_error", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), err=e.strerror, errno=e.errno)
			return

		test.model = model  # expose resolved ModelConfig to the script; restored on both exits below
		try:
			exec(compile(code, preproc, "exec"), ns)  # pylint: disable=exec-used  # runs user preproc script, rtl_buddy parity
		except Exception as e:
			test.model = name
			log.error("preproc_script_error", key=test.key, test_name=test.get_name(), preproc_path=str(preproc), exc_info=e)
			return

		test.model = name  # restore before forwarding so the test edge always carries the name string
		yield ("test", test)
		yield ("model", model)


@dataclass(frozen=True)
class FilelistEntry:
	path: str  # resolved/rewritten path; for a +libext+ entry, the coalesced value
	option: str | None  # option token: "-v ", "-y ", "+incdir+", "+libext+", or None

FILELIST_OPTION_RE = re.compile(r"^((?:-v|-y|-[Ff])\s+|(\+(?:incdir|libext)\+))?(.*)$")


class FilelistExtractMod:
	def run(self, source:ModelConfig|TestbenchConfig|TestConfig, base_dir:Path, unroll:bool = False):
		config = source.get_testbench() if isinstance(source, TestConfig) else source
		lines = config.get_filelist()
		entries = []
		libexts = {}
		def extract(lines_in, prefix_parent):
			for line in lines_in:
				line = line.strip()
				if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
					continue
				m = FILELIST_OPTION_RE.fullmatch(line)
				if not m or not m.group(3):
					log.error("filelist_malformed_line", line=line)
					continue
				if m.group(2):
					line_option, line_path = m.group(2), m.group(3)
				elif m.group(1):
					line_option, line_path = m.group(1).strip() + " ", m.group(3)
				else:
					line_option, line_path = None, m.group(3)
				line_path = os.path.expandvars(line_path)
				if line_option == '-f ':
					log.fatal("filelist_lower_f_not_allowed", line=line)
				elif line_option == '-F ' and unroll:
					path_next = os.path.join(prefix_parent, line_path)
					try:
						with open(path_next, encoding="utf-8") as f:
							extract(f.readlines(), os.path.dirname(path_next))
					except OSError as e:
						log.error("filelist_resolve_error", path=str(path_next), err=str(e))
				elif line_option == '+libext+':
					libexts.update(dict.fromkeys(line_path.split('+')))
				else:
					entries.append(FilelistEntry(os.path.join(prefix_parent, line_path), line_option))
		extract(lines, str(base_dir))
		if len(libexts) > 0:
			entries.append(FilelistEntry("+".join(libexts), "+libext+"))
		yield ("entries", entries)


class PrioritisedMergeMod:
	@serde
	class Config:
		priorities:dict[str, int]

	def __init__(self, config):
		self.priorities = config.priorities

	def run(self, **entries):
		missing = [name for name in entries if name not in self.priorities]
		if len(missing) > 0:
			log.fatal("unranked_merge_port", ports=missing)
		ordered = sorted(entries, key=lambda name: (self.priorities[name], name))
		return ("entries", [item for name in ordered for item in entries[name]])


def filelist_extract(lines_in, unroll, fpath):
	prefix_parent = os.path.dirname(fpath)
	entries = []
	libexts = set()
	for line in lines_in:
		line = line.strip()
		if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
			continue
		m = FILELIST_OPTION_RE.fullmatch(line)
		if not m or not m.group(3):
			log.error("filelist_malformed_line", line=line)
			continue
		if m.group(2):
			line_option, line_path = m.group(2), m.group(3)
		elif m.group(1):
			line_option, line_path = m.group(1).strip() + " ", m.group(3)
		else:
			line_option, line_path = None, m.group(3)
		line_path = os.path.expandvars(line_path)
		if line_option == '-f ':
			log.fatal("filelist_lower_f_not_allowed", line=line)
		elif line_option == '-F ' and unroll:
			path_next = os.path.join(prefix_parent, line_path)
			try:
				with open(path_next, encoding="utf-8") as f:
					entries.extend(filelist_extract(f.readlines(), unroll, path_next))
			except OSError as e:
				raise KeyError(f"F-include error {path_next}: {e}") from e
		elif line_option == '+libext+':
			libexts.update(line_path.split('+'))
		else:
			entries.append((os.path.join(prefix_parent, line_path), line_option))
	if len(libexts) != 0:
		entries.append(("+".join(libexts), "+libext+"))
	return entries


def filelist_process(entries, work_dir, deduplicate):
	out_lines = []
	for abs_path, line_option in entries:
		if line_option == '+libext+':
			line = f'+libext+{abs_path}\n'
		else:
			rel = os.path.relpath(abs_path, work_dir)
			if line_option in ('+incdir+', '-y '):
				if not os.path.isdir(abs_path):
					log.error("filelist_incdir_not_a_dir", path=abs_path)
			else:
				if not os.path.isfile(abs_path):
					log.error("filelist_file_not_found", path=abs_path)
			line = f'{line_option}{rel}\n' if line_option else f'{rel}\n'
		if deduplicate and line in out_lines:
			continue
		out_lines.append(line)
	return out_lines


class WriteFilelistMod:
	def run(self, test:TestConfig, model:ModelConfig, work_dir:Path):
		test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())
		path = Path(work_dir) / f"run.{test_tag}.f"
		try:
			model_path = model.get_model_path()
			model_dir = os.path.dirname(os.path.abspath(model_path)) if model_path else str(work_dir)
			entries = filelist_extract(model.get_filelist(), True, os.path.join(model_dir, "models.yaml"))
			entries.extend(filelist_extract(test.get_testbench().get_filelist(), True, str(Path(work_dir) / "tests.yaml")))
			lines = filelist_process(entries, str(work_dir), True)
			with open(path, "w", encoding="utf-8") as f:
				f.write("// rtl-buddy generated model filelist\n")
				f.writelines(lines)
			yield ("test", test)
			yield ("filelist", path)
		except FileNotFoundError:
			log.error("filelist_dir_not_found", key=test.key, test_name=test.get_name(), path=str(path))
		except IsADirectoryError:
			log.error("filelist_is_directory", key=test.key, test_name=test.get_name(), path=str(path))
		except PermissionError as e:
			log.error("filelist_permission_denied", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror)
		except (KeyError, AttributeError) as e:
			log.error("filelist_resolve_error", key=test.key, test_name=test.get_name(), path=str(path), err=str(e))
		except OSError as e:
			log.error("filelist_write_error", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror, errno=e.errno)


class RunProcessMod:
	@serde
	class Config:
		grace_s:float = 5.0  # SIGQUIT→SIGKILL escalation grace; per-node, default 5.0 s

	def __init__(self, config):
		self.grace_s = config.grace_s

	async def run(self, command:Command, work_dir:Path, timeout:float | None = None, env_ready:bool = True):
		with open(command.stdout_path, "wb") as out, open(command.stderr_path, "wb") as err:
			try:
				proc = await asyncio.create_subprocess_exec(
					*command.argv,
					stdout=out,
					stderr=err,
					preexec_fn=os.setpgrp,
					cwd=work_dir,
				)
			except (FileNotFoundError, PermissionError) as e:
				log.fatal("launch_failed", argv0=command.argv[0], exc_info=e)
			try:
				await asyncio.wait_for(proc.wait(), timeout)
				rc = proc.returncode
			except asyncio.TimeoutError:
				try:
					os.killpg(os.getpgid(proc.pid), signal.SIGQUIT)
				except ProcessLookupError:  # pragma: no cover — process-group already dead (ESRCH); race, see docs/testing.md
					pass
				try:
					await asyncio.wait_for(proc.wait(), self.grace_s)
				except asyncio.TimeoutError:
					try:
						os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
					except ProcessLookupError:  # pragma: no cover — process-group already dead (ESRCH); race, see docs/testing.md
						pass
					await proc.wait()
				rc = None
			except asyncio.CancelledError:
				try:
					os.killpg(os.getpgid(proc.pid), signal.SIGQUIT)
				except ProcessLookupError:  # pragma: no cover — process-group already dead (ESRCH); race, see docs/testing.md
					pass
				try:
					await asyncio.shield(asyncio.wait_for(proc.wait(), self.grace_s))
				except (asyncio.TimeoutError, asyncio.CancelledError):
					try:
						os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
					except ProcessLookupError:  # pragma: no cover — process-group already dead (ESRCH); race, see docs/testing.md
						pass
					await asyncio.shield(proc.wait())
				raise
		return Proc(command.key, rc=rc, stdout_path=command.stdout_path, stderr_path=command.stderr_path)


class BuildCompileCmdMod:
	def run(self, test:TestConfig, filelist:Path, builder_cfg:RtlBuilderConfig, logs_dir:Path, work_dir:Path, builder_mode:str = "debug"):
		test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test.get_name())
		exe = builder_cfg.get_exe()
		is_verilator = os.path.basename(exe).startswith("verilator")
		build_dir = str(Path(work_dir) / f"obj_dir_{test_tag}")
		simv = f"{build_dir}/simv" if is_verilator else builder_cfg.get_simv()
		argv = [exe, *builder_cfg.get_compile_time_opts(builder_mode)]
		if is_verilator:
			argv += ["--Mdir", build_dir]
		plusdefines = []
		pd = test.get_plusdefines()
		if pd is not None:
			for k, v in pd.items():
				plusdefines.append(f"+define+{k}={v}" if v is not None else f"+define+{k}")
		argv += [*plusdefines, "-f", str(filelist)]
		yield ("test", test)
		yield ("simv", simv)
		yield ("command", Command(test.key, argv=argv, stdout_path=str(logs_dir / f"{test_tag}.compile.log"), stderr_path=str(logs_dir / f"{test_tag}.compile.err")))


class InterpretCompileMod:
	def run(self, test:TestConfig, simv:str, proc:Proc):
		if proc.rc == 0:
			yield ("test", test)
			yield ("simv", simv)
			return
		stderr_tail = None
		try:
			with open(proc.stderr_path, "r", encoding="utf-8", errors="replace") as f:
				content = f.read()
			stderr_tail = content[-4096:] if len(content) > 4096 else content
		except OSError:
			pass
		log_kw = {"key": test.key, "test_name": test.get_name(), "rc": proc.rc, "stderr_path": str(proc.stderr_path)}
		if stderr_tail is not None:
			log_kw["stderr_tail"] = stderr_tail
		log.error("compile_failed", **log_kw)
