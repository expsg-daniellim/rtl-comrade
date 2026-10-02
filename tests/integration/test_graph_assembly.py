"""Integration tests: graphs/test.yaml, graphs/randtest.yaml, and graphs/regression.yaml load, validate, and appear in --help output.

Checks that the assembled graph YAML is internally consistent (no dangling manifest
references, no cycles, no overloaded inputs) and that the CLI wiring is correct.
"""

import re
import subprocess
from pathlib import Path

from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph

_PROJECT_ROOT = Path(__file__).parents[2]
_GRAPH_PATH = _PROJECT_ROOT / "graphs" / "test.yaml"
_RANDTEST_GRAPH_PATH = _PROJECT_ROOT / "graphs" / "randtest.yaml"
_REGRESSION_GRAPH_PATH = _PROJECT_ROOT / "graphs" / "regression.yaml"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text:str) -> str:
	"""Remove ANSI colour/style escape sequences so substring checks match regardless of terminal colour.

	rich force-enables colour under GitHub Actions (``GITHUB_ACTIONS`` in the environment) even when
	stdout is a captured pipe, styling option names as separate escape-wrapped spans (e.g. ``--test-config``
	renders as ``-``/``-test``/``-config``), so the raw string is not a contiguous substring of the help output.
	"""

	return _ANSI.sub("", text)


def test_graph_config_loads(logging_handler):
	"""GraphConfig.from_file resolves all module and contract names without error."""
	config = GraphConfig.from_file(_GRAPH_PATH)
	assert config is not None
	assert not logging_handler.failure


def test_graph_constructs(logging_handler):
	"""Graph.from_config validates the assembled graph: no cycles, no overloaded inputs."""
	config = GraphConfig.from_file(_GRAPH_PATH)
	graph = Graph.from_config(config)
	assert graph is not None
	assert not logging_handler.failure


def test_help_lists_test_command():
	"""rtl-comrade --help lists the test subcommand with the correct help string."""
	result = subprocess.run(
		["uv", "run", "rtl-comrade", "--help"],
		cwd=_PROJECT_ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0
	output = strip_ansi(result.stdout)
	assert "test" in output
	assert "Compile and simulate a SystemVerilog/UVM test suite." in output


def test_subcommand_help_lists_cli_edges():
	"""rtl-comrade test --help lists every CLI edge with correct names."""
	result = subprocess.run(
		["uv", "run", "rtl-comrade", "test", "--help"],
		cwd=_PROJECT_ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0
	output = strip_ansi(result.stdout)
	# options (typer renders these as --<hyphenated-name>)
	assert "--test-config" in output
	assert "--logs-dir" in output
	assert "--builder" in output
	assert "--list" in output
	assert "--rnd-new" in output
	assert "--rnd-last" in output
	assert "--builder-mode" in output
	assert "--early-stop" in output
	# positional argument (option: false — rendered uppercase in typer help)
	assert "TEST_NAME" in output


def test_randtest_graph_constructs(logging_handler):
	"""graphs/randtest.yaml resolves every module and contract and validates: no cycles, overloaded inputs, or unknown persistent ports."""
	config = GraphConfig.from_file(_RANDTEST_GRAPH_PATH)
	graph = Graph.from_config(config)
	assert graph is not None
	assert not logging_handler.failure


def test_randtest_graph_node_delta(logging_handler):
	"""randtest.yaml swaps seed-mode for derive-runs and drops the list-mode nodes; every other test.yaml node carries over."""
	test_ids = { n.id for n in GraphConfig.from_file(_GRAPH_PATH).nodes }
	randtest_ids = { n.id for n in GraphConfig.from_file(_RANDTEST_GRAPH_PATH).nodes }
	assert "derive-runs" in randtest_ids
	assert not randtest_ids & { "seed-mode", "route-list", "list-names" }
	assert randtest_ids == (test_ids - { "seed-mode", "route-list", "list-names" }) | { "derive-runs" }
	assert not logging_handler.failure


def test_help_lists_randtest_command():
	"""rtl-comrade --help lists the randtest subcommand with the correct help string."""
	result = subprocess.run(
		["uv", "run", "rtl-comrade", "--help"],
		cwd=_PROJECT_ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0
	output = strip_ansi(result.stdout)
	assert "randtest" in output
	assert "Random-seed testing of a single test." in output


def test_randtest_subcommand_help_lists_cli_edges():
	"""rtl-comrade randtest --help lists every randtest CLI parameter with its type and default, and none of the removed test options."""
	result = subprocess.run(
		["uv", "run", "rtl-comrade", "randtest", "--help"],
		cwd=_PROJECT_ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0
	lines = strip_ansi(result.stdout).splitlines()

	def row(name:str) -> str:
		"""Return the help row whose first token is ``name``."""

		return next(line for line in lines if line.strip("│* ").startswith(name))

	# positional arguments (option: false — typer lists these by their lowercase names)
	assert "[required]" in row("test_name")
	assert "[default: 2]" in row("rnd_cnt")
	# options (typer renders these as --<hyphenated-name>)
	assert "-r" in row("--rnd-rpt") and "INTEGER" in row("--rnd-rpt") and "[default: -1]" in row("--rnd-rpt")
	assert "-c" in row("--test-config") and "[default: tests.yaml]" in row("--test-config")
	assert "[default: logs]" in row("--logs-dir")
	assert "-B" in row("--builder ")
	assert "-M" in row("--builder-mode") and "[default: debug]" in row("--builder-mode")
	assert "-E" in row("--early-stop") and "[default: post]" in row("--early-stop")
	output = "\n".join(lines)
	assert "--rnd-new" not in output
	assert "--rnd-last" not in output
	assert "--list" not in output


def test_regression_graph_constructs(logging_handler):
	"""graphs/regression.yaml resolves every module and contract and validates: no cycles, overloaded inputs, or unknown persistent ports."""
	config = GraphConfig.from_file(_REGRESSION_GRAPH_PATH)
	graph = Graph.from_config(config)
	assert graph is not None
	assert not logging_handler.failure


def test_regression_graph_node_delta(logging_handler):
	"""regression.yaml swaps seed-mode, work-dir, and ensure-logs for the suite pipeline nodes, drops list mode, and adds the summary-metadata loggers; every other test.yaml node carries over."""
	removed = { "seed-mode", "route-list", "list-names", "work-dir", "ensure-logs" }
	added = { "resolve-reg-path", "parse-reg", "const-seed-mode", "extract-dir", "extract-dir-post", "log-builder", "log-builder-mode", "log-suite" }
	test_ids = { n.id for n in GraphConfig.from_file(_GRAPH_PATH).nodes }
	regression_ids = { n.id for n in GraphConfig.from_file(_REGRESSION_GRAPH_PATH).nodes }
	assert added <= regression_ids
	assert not regression_ids & removed
	assert regression_ids == (test_ids - removed) | added
	assert not logging_handler.failure


def test_regression_graph_summary_wiring(logging_handler):
	"""regression.yaml has the three summary-metadata logger nodes and routes its logging block to the regression summary processors."""
	config = GraphConfig.from_file(_REGRESSION_GRAPH_PATH)
	modules = { n.id: n.module.name for n in config.nodes }
	assert all(modules[node] == "logger" for node in ("log-builder", "log-builder-mode", "log-suite"))
	assert [ (h.path, h.name) for h in config.logging.handlers ] == [(Path("log/regression_summary.py"), "FileRegressionSummaryProcessor"), (Path("log/regression_summary.py"), "ConsoleRegressionSummaryProcessor")]
	assert not logging_handler.failure


def test_help_lists_regression_command():
	"""rtl-comrade --help lists the regression subcommand with the correct help string."""
	result = subprocess.run(
		["uv", "run", "rtl-comrade", "--help"],
		cwd=_PROJECT_ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0
	output = strip_ansi(result.stdout)
	assert "regression" in output
	assert "Run regression suites with level filtering." in output


def test_regression_subcommand_help_lists_cli_edges():
	"""rtl-comrade regression --help lists every regression CLI parameter with its type and default, and none of the removed test options."""
	result = subprocess.run(
		["uv", "run", "rtl-comrade", "regression", "--help"],
		cwd=_PROJECT_ROOT,
		capture_output=True,
		text=True,
		check=False,
	)
	assert result.returncode == 0
	lines = strip_ansi(result.stdout).splitlines()

	def row(name:str) -> str:
		"""Return the help row whose first token is ``name``."""

		return next(line for line in lines if line.strip("│* ").startswith(name))

	assert "-c" in row("--reg-config") and "TEXT" in row("--reg-config") and "[default:" not in row("--reg-config")
	assert "-l" in row("--reg-level") and "INTEGER" in row("--reg-level") and "[default: 0]" in row("--reg-level")
	assert "-s" in row("--start-level") and "INTEGER" in row("--start-level") and "[default: 0]" in row("--start-level")
	assert "-L" in row("--logs-dir") and "[default: logs]" in row("--logs-dir")
	assert "-B" in row("--builder ") and "[default:" not in row("--builder ")
	assert "-M" in row("--builder-mode") and "[default: reg]" in row("--builder-mode")
	assert "-E" in row("--early-stop") and "[default: post]" in row("--early-stop")
	output = "\n".join(lines)
	assert "TEST_NAME" not in output and "test_name" not in output
	assert "--list" not in output
	assert "--rnd-new" not in output
	assert "--rnd-last" not in output
	assert "--test-config" not in output
