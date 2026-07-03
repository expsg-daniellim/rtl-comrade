"""Integration tests: graphs/test.yaml loads, validates, and appears in --help output.

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
