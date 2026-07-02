"""Tests for modules/rtl_buddy/build.py — RunProcessMod."""

import asyncio
import importlib.util
import os
import signal
from pathlib import Path

import pytest
import typer

from rtl_comrade.testing import run_module_scenario
from modules.rtl_buddy.schema import Command, KeyedValue, Proc

_spec = importlib.util.spec_from_file_location(
	"modules_rtl_buddy_build",
	Path(__file__).parent.parent / "rtl_buddy" / "build.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RunProcessMod = _mod.RunProcessMod


def _cmd(key, argv, tmp_path, out_name="out.txt", err_name="err.txt"):
	return Command(
		key=key,
		argv=argv,
		stdout_path=tmp_path / out_name,
		stderr_path=tmp_path / err_name,
	)


# ---------------------------------------------------------------------------
# Normal exit (rc 0) — Lifecycle 2a
# ---------------------------------------------------------------------------


async def test_normal_exit(tmp_path, logging_handler):
	cmd = _cmd("k1", ["sh", "-c", "echo hi; exit 0"], tmp_path)
	await run_module_scenario(
		RunProcessMod,
		input_sequence=[{"command": cmd, "work_dir": tmp_path, "timeout": None}],
		expected_emissions={"default": [Proc(key="k1", rc=0, stdout_path=cmd.stdout_path, stderr_path=cmd.stderr_path)]},
		config=RunProcessMod.Config(),
		timeout=10.0,
	)
	assert cmd.stdout_path.read_bytes() == b"hi\n"
	assert not logging_handler.failure


# ---------------------------------------------------------------------------
# Subprocess runs in work_dir, not process CWD
# ---------------------------------------------------------------------------


async def test_work_dir_isolation(tmp_path, monkeypatch):
	other = tmp_path / "other"
	other.mkdir()
	monkeypatch.chdir(other)
	out = tmp_path / "out.txt"
	err = tmp_path / "err.txt"
	cmd = Command(key="k1", argv=["sh", "-c", "pwd > ran_here; : > relative_artifact"], stdout_path=out, stderr_path=err)
	mod = RunProcessMod(RunProcessMod.Config())
	result = await mod.run(command=cmd, work_dir=tmp_path)
	assert isinstance(result, Proc)
	assert result.rc == 0
	assert (tmp_path / "relative_artifact").exists()
	assert not (other / "relative_artifact").exists()
	ran_here = (tmp_path / "ran_here").read_text().strip()
	assert Path(ran_here).resolve() == tmp_path.resolve()


# ---------------------------------------------------------------------------
# Non-zero exit — no log emitted
# ---------------------------------------------------------------------------


async def test_nonzero_exit(tmp_path, logging_handler):
	cmd = _cmd("k1", ["sh", "-c", "exit 7"], tmp_path)
	mod = RunProcessMod(RunProcessMod.Config())
	result = await mod.run(command=cmd, work_dir=tmp_path)
	assert isinstance(result, Proc)
	assert result.rc == 7
	assert not logging_handler.failure


# ---------------------------------------------------------------------------
# External kill → rc = -signum (int, not None) — Lifecycle 2a externally-killed
# ---------------------------------------------------------------------------


async def test_external_kill(tmp_path):
	pid_file = tmp_path / "pid.txt"
	out = tmp_path / "out.txt"
	err = tmp_path / "err.txt"
	cmd = Command(key="k1", argv=["sh", "-c", f"echo $$ > {pid_file}; sleep 30"], stdout_path=out, stderr_path=err)
	mod = RunProcessMod(RunProcessMod.Config())

	run_task = asyncio.create_task(mod.run(command=cmd, work_dir=tmp_path))
	for _ in range(40):
		await asyncio.sleep(0.05)
		if pid_file.exists():
			break
	assert pid_file.exists(), "subprocess did not write pid in time"

	child_pid = int(pid_file.read_text().strip())
	os.kill(child_pid, signal.SIGKILL)

	result = await run_task
	assert isinstance(result, Proc)
	assert result.rc == -signal.SIGKILL


# ---------------------------------------------------------------------------
# Timeout: partial output preserved, rc is None, no stale children — Lifecycle 2b → 3a
# ---------------------------------------------------------------------------


async def test_timeout_partial_output(tmp_path):
	cmd = _cmd("k1", ["sh", "-c", "echo partial; sleep 5"], tmp_path)
	mod = RunProcessMod(RunProcessMod.Config(grace_s=1.0))
	result = await mod.run(command=cmd, work_dir=tmp_path, timeout=KeyedValue("k1", 0.1))
	assert isinstance(result, Proc)
	assert result.rc is None
	assert b"partial" in cmd.stdout_path.read_bytes()
	try:
		pid, _ = os.waitpid(-1, os.WNOHANG)
		assert pid == 0
	except ChildProcessError:
		pass


# ---------------------------------------------------------------------------
# Timeout: uncooperative child (ignores SIGQUIT) → SIGKILL escalation — Lifecycle 3a
# ---------------------------------------------------------------------------


async def test_timeout_sigkill_escalation(tmp_path):
	cmd = _cmd("k1", ["sh", "-c", "trap '' QUIT; sleep 30"], tmp_path)
	mod = RunProcessMod(RunProcessMod.Config(grace_s=0.5))
	result = await mod.run(command=cmd, work_dir=tmp_path, timeout=KeyedValue("k1", 0.1))
	assert isinstance(result, Proc)
	assert result.rc is None


# ---------------------------------------------------------------------------
# Organic exit 4444 is not the timeout indicator
# ---------------------------------------------------------------------------


async def test_organic_4444_not_timeout(tmp_path):
	cmd = _cmd("k1", ["sh", "-c", "exit 4444"], tmp_path)
	mod = RunProcessMod(RunProcessMod.Config())
	result = await mod.run(command=cmd, work_dir=tmp_path)
	assert isinstance(result, Proc)
	assert isinstance(result.rc, int)  # POSIX truncates to 8 bits; any int is not None
	assert result.rc is not None


# ---------------------------------------------------------------------------
# Launch failure: FileNotFoundError → log.fatal → typer.Exit
# ---------------------------------------------------------------------------


async def test_launch_failure(tmp_path, logging_handler):
	cmd = _cmd("k1", ["./nonexistent-binary"], tmp_path)
	with pytest.raises(typer.Exit):
		await run_module_scenario(
			RunProcessMod,
			input_sequence=[{"command": cmd, "work_dir": tmp_path}],
			expected_emissions={},
			config=RunProcessMod.Config(),
			timeout=5.0,
		)


# ---------------------------------------------------------------------------
# Cancellation cleanup — Lifecycle 2c → 3b
# ---------------------------------------------------------------------------


async def test_cancellation_cleanup(tmp_path):
	out = tmp_path / "out.txt"
	err = tmp_path / "err.txt"
	# Child writes output then ignores SIGQUIT, ensuring SIGKILL escalation
	cmd = Command(key="k1", argv=["sh", "-c", "echo partial; trap '' QUIT; sleep 30"], stdout_path=out, stderr_path=err)
	mod = RunProcessMod(RunProcessMod.Config(grace_s=0.5))

	task = asyncio.create_task(mod.run(command=cmd, work_dir=tmp_path))
	await asyncio.sleep(0.2)  # let subprocess start and write output
	task.cancel()

	with pytest.raises(asyncio.CancelledError):
		await task

	# Partial stdout preserved on disk
	assert b"partial" in out.read_bytes()
	# No zombie children
	try:
		pid, _ = os.waitpid(-1, os.WNOHANG)
		assert pid == 0
	except ChildProcessError:
		pass


# ---------------------------------------------------------------------------
# Process-group reach: grandchild also dies on timeout
# ---------------------------------------------------------------------------


async def test_process_group_reach(tmp_path):
	gc_pid_file = tmp_path / "gc_pid.txt"
	out = tmp_path / "out.txt"
	err = tmp_path / "err.txt"
	# Parent ignores SIGQUIT so it survives long enough for SIGKILL escalation to reach
	# the whole process group; grandchild (background job) also ignores SIGQUIT per POSIX
	script = f"trap '' QUIT; sh -c 'echo $$ > {gc_pid_file}; sleep 30' & sleep 30"
	cmd = Command(key="k1", argv=["sh", "-c", script], stdout_path=out, stderr_path=err)
	mod = RunProcessMod(RunProcessMod.Config(grace_s=0.5))

	result = await mod.run(command=cmd, work_dir=tmp_path, timeout=KeyedValue("k1", 0.1))
	assert result.rc is None

	assert gc_pid_file.exists(), "grandchild did not write pid before timeout"
	gc_pid = int(gc_pid_file.read_text().strip())

	# Allow init to reap grandchild zombie
	await asyncio.sleep(0.2)
	with pytest.raises(ProcessLookupError):
		os.kill(gc_pid, 0)


# ---------------------------------------------------------------------------
# Opaque key passthrough: output key == input command.key
# ---------------------------------------------------------------------------


async def test_key_passthrough(tmp_path):
	cmd = _cmd("my-key-42", ["sh", "-c", "exit 0"], tmp_path)
	mod = RunProcessMod(RunProcessMod.Config())
	result = await mod.run(command=cmd, work_dir=tmp_path)
	assert isinstance(result, Proc)
	assert result.key == "my-key-42"


# ---------------------------------------------------------------------------
# Emits paths, not file handles
# ---------------------------------------------------------------------------


async def test_emits_paths_not_handles(tmp_path):
	cmd = _cmd("k1", ["sh", "-c", "exit 0"], tmp_path)
	mod = RunProcessMod(RunProcessMod.Config())
	result = await mod.run(command=cmd, work_dir=tmp_path)
	assert isinstance(result, Proc)
	assert isinstance(result.stdout_path, Path)
	assert isinstance(result.stderr_path, Path)


# ---------------------------------------------------------------------------
# env_ready accepted and ignored
# ---------------------------------------------------------------------------


async def test_env_ready_ignored(tmp_path):
	cmd = _cmd("k1", ["sh", "-c", "exit 0"], tmp_path)
	mod = RunProcessMod(RunProcessMod.Config())
	result_with = await mod.run(command=cmd, work_dir=tmp_path, env_ready=True)
	cmd2 = _cmd("k2", ["sh", "-c", "exit 0"], tmp_path, out_name="out2.txt", err_name="err2.txt")
	result_without = await mod.run(command=cmd2, work_dir=tmp_path)
	assert isinstance(result_with, Proc)
	assert isinstance(result_without, Proc)
	assert result_with.rc == 0
	assert result_without.rc == 0
