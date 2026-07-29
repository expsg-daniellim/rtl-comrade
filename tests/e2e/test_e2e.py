"""End-to-end parity tests: rtl-comrade test vs rtl_buddy test.

Drives the committed suite fixtures under tests/e2e/fixtures/proj (ported from
rtl-buddy-proj-template) and compares rtl-comrade's
exit code and per-test verdicts to rtl_buddy's captured reference output
(tests/e2e/captures/, pinned rtl_buddy v1.4.0), with the deliberate divergences
from [07] applied. The captures stand in for the rtl_buddy reference binary,
which is not installed in CI.

Deliberate divergences from rtl_buddy (expected mismatches):
- --early-stop exits 0 (rtl_buddy exits 1; [07] Notable divergences).
- --early-stop pre/comp desc is "Stopped early at pre"/"…comp" not "…preproc"/"…compile".
- Compile logs are written to logs/ (rtl_buddy only captures in memory; [07 settled 12]).
"""

import re
import subprocess
from pathlib import Path

import pytest

from modules.rtl_buddy.schema import Proc
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig
from modules.rtl_buddy.sim import ParseLogMod

_PROJECT_ROOT = Path(__file__).parents[2]
# Suite fixtures are committed under tests/e2e/fixtures/proj (ported from the
# rtl-buddy-proj-template). The directory layout
# mirrors the template so the tests.yaml/models.yaml relative paths resolve.
_FIXTURE_PROJ = Path(__file__).parent / "fixtures" / "proj"
_SANDBOX = _FIXTURE_PROJ / "verif" / "sandbox"
_LAZY_MODEL_SUITE = _FIXTURE_PROJ / "verif" / "lazy_model"
_VENV_BIN = _PROJECT_ROOT / ".venv" / "bin"
_RC_BIN = str(_VENV_BIN / "rtl-comrade")
_CAPTURES = Path(__file__).parent / "captures"


def _run_rc(args, *, cwd=None):
	return subprocess.run(
		[_RC_BIN, *args],
		cwd=cwd or _SANDBOX,
		capture_output=True,
		text=True,
		check=False,
	)


def _ref(name):
	"""Load a captured rtl_buddy reference result (return code, ANSI-stripped stderr).

	Captures live under tests/e2e/captures/ and replace invoking the rtl_buddy
	reference binary, which is not installed in CI. Generated from the pinned
	rtl_buddy v1.4.0 against these fixtures; stdout is not captured (it carries a
	non-deterministic git banner and compile/run timings the tests never read).
	"""
	rc = int((_CAPTURES / f"{name}.rc").read_text())
	err_path = _CAPTURES / f"{name}.err"
	return rc, err_path.read_text() if err_path.exists() else ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_ansi(s):
	"""Strip ANSI colour codes from a string."""
	return re.sub(r"\x1b\[[0-9;]*m", "", s)


def _verdicts(stdout):
	"""Return {test_name: (verdict, desc)} from the summary table in stdout.

	The summary table lines look like (with or without ANSI codes):
		basic	  PASS	(nwrn=	0)
		compile_fail	 FAIL  Compile failed
		basic	  NA	Stopped early at pre
	"""
	result = {}
	for line in _strip_ansi(stdout).splitlines():
		m = re.match(r"^\s*(\S+)\s+(PASS|FAIL|NA)\s+(.*?)\s*$", line)
		if m:
			result[m.group(1)] = (m.group(2), m.group(3).strip())
	return result


# ---------------------------------------------------------------------------
# Parity scenario 1: --list
# ---------------------------------------------------------------------------

def test_list_exit_and_names():
	"""rtl-comrade test --list exits 0 and prints the test names in declaration order.

	Reference: rtl_buddy test --list exits 0, prints five names.
	Captured reference: tests/e2e/captures/list_names.txt.
	"""
	expected = (_CAPTURES / "list_names.txt").read_text().strip()

	ref_rc, _ = _ref("list")
	assert ref_rc == 0

	result = _run_rc(["test", "--list"])
	assert result.returncode == 0, (
		f"--list exited {result.returncode} (expected 0); stderr: {result.stderr[-2000:]}"
	)
	assert result.stdout.strip() == expected, (
		f"--list stdout mismatch; got: {result.stdout!r}"
	)


# ---------------------------------------------------------------------------
# Parity scenario 2: passing run
# ---------------------------------------------------------------------------

def test_passing_run_exit_and_verdict():
	"""rtl-comrade test basic exits 0 with per-test PASS verdict.

	Reference: rtl_buddy test basic exits 0, summary shows PASS.
	"""
	result = _run_rc(["test", "basic"])
	assert result.returncode == 0, (
		f"basic exited {result.returncode} (expected 0); stderr: {result.stderr[-2000:]}"
	)
	vs = _verdicts(result.stdout)
	assert "basic" in vs, f"No 'basic' row in summary; stdout: {result.stdout}"
	assert vs["basic"][0] == "PASS", f"Expected PASS for basic, got {vs['basic']}"


def test_passing_run_artifacts(tmp_path):
	"""Passing run produces .log/.err/.randseed under logs/ and test.* symlinks.

	Artifact parity: rtl-comrade and rtl_buddy both produce logs/basic.log,
	logs/basic.err, logs/basic.randseed; test.log/test.err/test.randseed symlinks
	(under work_dir = CWD) point at those files (spec [08e]).
	"""
	result = _run_rc(["test", "basic"], cwd=_SANDBOX)
	assert result.returncode == 0, (
		f"basic exited {result.returncode}; stderr: {result.stderr[-2000:]}"
	)
	logs = _SANDBOX / "logs"
	for stem in ("basic.log", "basic.err", "basic.randseed"):
		assert (logs / stem).exists(), f"Missing artifact: logs/{stem}"
	for link in ("test.log", "test.err", "test.randseed"):
		p = _SANDBOX / link
		assert p.is_symlink(), f"{link} is not a symlink"
		assert p.resolve() == (logs / link.replace("test.", "basic.")).resolve(), (
			f"{link} does not point to logs/basic.{link.split('.', 1)[1]}"
		)


# ---------------------------------------------------------------------------
# Parity scenario 3: compile-fail
# ---------------------------------------------------------------------------

def test_compile_fail_exit_and_verdict():
	"""rtl-comrade test compile_fail exits non-zero with per-test FAIL verdict.

	Reference: rtl_buddy test compile_fail exits 1, summary shows FAIL.
	Compile log is persisted under logs/ ([07 settled 12]) — new behaviour vs rtl_buddy.
	"""
	ref_rc, _ = _ref("compile_fail")
	assert ref_rc != 0

	result = _run_rc(["test", "compile_fail"])
	assert result.returncode != 0, (
		f"compile_fail should exit non-zero; stdout: {result.stdout}"
	)
	vs = _verdicts(result.stdout)
	assert "compile_fail" in vs, f"No 'compile_fail' row in summary; stdout: {result.stdout}"
	assert vs["compile_fail"][0] == "FAIL", (
		f"Expected FAIL for compile_fail, got {vs['compile_fail']}"
	)


def test_compile_fail_log_persisted():
	"""Compile log is written to logs/ even on failure ([07 settled 12]).

	New behaviour relative to rtl_buddy (which only captures compile output in memory).
	"""
	_run_rc(["test", "compile_fail"])
	logs = _SANDBOX / "logs"
	assert (logs / "compile_fail.compile.log").exists() or (logs / "compile_fail.compile.err").exists(), (
		"Expected compile_fail.compile.log or .err under logs/"
	)


# ---------------------------------------------------------------------------
# Parity scenario 4: sim-timeout
# ---------------------------------------------------------------------------

def test_sim_timeout_exit_and_verdict():
	"""rtl-comrade test sim_timeout exits non-zero with FAIL/SimTimeout verdict.

	Reference: rtl_buddy test sim_timeout exits 1, summary shows FAIL.
	The ``rc is None`` timeout path (vs rtl_buddy's 4444 sentinel) is [07 settled 23].
	"""
	ref_rc, _ = _ref("sim_timeout")
	assert ref_rc != 0

	result = _run_rc(["test", "sim_timeout"])
	assert result.returncode != 0, (
		f"sim_timeout should exit non-zero; stdout: {result.stdout}"
	)
	vs = _verdicts(result.stdout)
	assert "sim_timeout" in vs, f"No 'sim_timeout' row in summary; stdout: {result.stdout}"
	assert vs["sim_timeout"][0] == "FAIL", (
		f"Expected FAIL for sim_timeout, got {vs['sim_timeout']}"
	)


# ---------------------------------------------------------------------------
# Parity scenario 5: --early-stop at each phase
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase,rb_desc,rc_desc", [
	("pre",	 "Stopped early at preproc",  "Stopped early at pre"),
	("comp", "Stopped early at compile",  "Stopped early at comp"),
	("sim",	 "Stopped early at sim",	  "Stopped early at sim"),
])
def test_early_stop(phase, rb_desc, rc_desc):
	"""--early-stop exits 0 (deliberate divergence from rtl_buddy's 1), per-test NA.

	Deliberate divergences ([07] Notable divergences):
	- Exit code: rtl-comrade exits 0, rtl_buddy exits 1 (NA is not a failure).
	- Desc for pre/comp: rtl-comrade uses phase token ("pre"/"comp") not rtl_buddy's
	  "preproc"/"compile" wording. Only "sim" desc is identical between the two.
	"""
	ref_rc, ref_err = _ref(f"early_{phase}")
	assert ref_rc == 1, f"rtl_buddy --early-stop {phase} should exit 1"
	ref_vs = _verdicts(ref_err)
	assert "basic" in ref_vs, f"No 'basic' row in rtl_buddy capture; stderr: {ref_err}"
	assert ref_vs["basic"][0] == "NA"
	assert rb_desc in ref_vs["basic"][1], (
		f"Expected rtl_buddy desc '{rb_desc}', got '{ref_vs['basic'][1]}'"
	)

	result = _run_rc(["test", "--early-stop", phase, "basic"])
	assert result.returncode == 0, (
		f"--early-stop {phase} should exit 0 (deliberate divergence); "
		f"stderr: {result.stderr[-2000:]}"
	)
	rc_vs = _verdicts(result.stdout)
	assert "basic" in rc_vs, f"No 'basic' row in rtl-comrade output; stdout: {result.stdout}"
	assert rc_vs["basic"][0] == "NA", f"Expected NA, got {rc_vs['basic'][0]}"
	assert rc_desc in rc_vs["basic"][1], (
		f"Expected desc '{rc_desc}', got '{rc_vs['basic'][1]}'"
	)


# ---------------------------------------------------------------------------
# Lazy load-model: skipped test's broken models.yaml is never read
# ---------------------------------------------------------------------------

def test_lazy_load_model():
	"""Unselected tests do not trip on a broken models.yaml (lazy load, [07 settled 8]).

	Drives the lazy_model suite: `runnable` has a valid model; `skip_broken_model`
	has an intentionally-broken models.yaml. Passing `runnable` as test_name selects
	only that test; `skip_broken_model` is never fed to load-model, so the broken
	YAML is never parsed and the run exits 0.

	rtl_buddy loads all models eagerly at suite-parse, so it would error on this
	fixture regardless — the lazy_model suite lives in its own directory precisely
	to keep it from being used with rtl_buddy directly.
	"""
	result = _run_rc(["test", "runnable"], cwd=_LAZY_MODEL_SUITE)
	assert result.returncode == 0, (
		f"lazy_model suite should exit 0 (skip_broken_model filtered before load-model); "
		f"stderr: {result.stderr[-2000:]}"
	)
	vs = _verdicts(result.stdout)
	assert "runnable" in vs, f"Expected 'runnable' in summary; stdout: {result.stdout}"
	assert vs["runnable"][0] == "PASS", f"Expected runnable=PASS, got {vs['runnable']}"
	assert "skip_broken_model" not in vs, (
		"skip_broken_model should not appear in summary (filtered out before load-model)"
	)


# ---------------------------------------------------------------------------
# ParseLog corrections ([07 settled 15])
# ---------------------------------------------------------------------------

def _make_test_cfg(name="t"):
	tb = TestbenchConfig(name="tb", filelist=[])
	return TestConfig(
		name=name, desc="", model="m", model_path="models.yaml",
		suite_dir=Path("."), reglvl=None, pa=None, pd=None,
		uvm=None, preproc_path=None, postproc_path=None, sweep_path=None,
		tb=tb, timeout=None,
	)


def _make_proc(tmp_path, key, content):
	log_file = tmp_path / f"{key}.log"
	log_file.write_text(content)
	return Proc(key=key, rc=0, stdout_path=log_file, stderr_path=tmp_path / f"{key}.err")


def test_parselog_fail_wins_over_pass(tmp_path, logging_handler):
	"""FAIL wins over PASS when both appear in the log ([07 settled 15] correction 2).

	rtl_buddy's VlogPost uses two independent ``if`` blocks so PASS can override FAIL
	when PASS appears later. ParseLogMod corrects this with ``if…elif``.
	"""
	test = _make_test_cfg("t")
	proc = _make_proc(tmp_path, test.key, "PASS result OK\nFAIL run ended\nERR: something wrong\n")
	mod = ParseLogMod()
	result = mod.run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parselog_passthrough_not_misclassified(tmp_path, logging_handler):
	"""PASSTHROUGH does not misclassify as PASS ([07 settled 15] correction 1).

	rtl_buddy's VlogPost uses ``re.search(r'^PASS\\s*(.*)')`` which matches
	``PASSTHROUGH`` (no word boundary). ParseLogMod uses ``re.match(r'PASS\\b\\s*(.*)')``
	so PASSTHROUGH is not treated as a PASS line.
	"""
	test = _make_test_cfg("t")
	proc = _make_proc(tmp_path, test.key, "PASSTHROUGH all checks\n")
	mod = ParseLogMod()
	result = mod.run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parselog_fail_without_err_no_crash(tmp_path, logging_handler):
	"""FAIL without ERR:/FAT: does not crash ([07 settled 15] correction 3).

	rtl_buddy's VlogPost does ``match_err.group(2)`` even when ``match_err`` is None,
	causing an AttributeError. ParseLogMod guards with ``if match_err is not None``.
	"""
	test = _make_test_cfg("t")
	proc = _make_proc(tmp_path, test.key, "FAIL test ended badly\n")
	mod = ParseLogMod()
	result = mod.run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# Concurrency hole note (fixed-simv builders)
# ---------------------------------------------------------------------------

def test_concurrency_hole_documented():
	"""Placeholder asserting the fixed-simv concurrency limitation is acknowledged.

	On non-verilator (fixed-simv) builders, concurrent multi-test runs can silently
	overwrite one test's binary with another's. There is no built-in serialisation
	([07 deferred 17]). Validate such builders one test per invocation (operational
	workaround). This test simply asserts the limitation is recorded in docs/divergences.md.
	"""
	divergences = _PROJECT_ROOT / "docs" / "divergences.md"
	assert divergences.exists(), "docs/divergences.md must exist"
	text = divergences.read_text()
	assert "fixed-simv" in text or "concurrency" in text.lower(), (
		"divergences.md must document the fixed-simv concurrency hole ([07 deferred 17])"
	)
