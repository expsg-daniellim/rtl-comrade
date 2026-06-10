"""Integration test: load the real modules/ and contracts/ directories end-to-end.

These tests catch loader regressions that are invisible to the rest of the suite,
which always writes minimal, dependency-free plugins to tmp_path.  The scenarios
below copy the actual source trees into an isolated tmp_path, construct a config
equivalent to graph2.yaml, and run the graph.

What this covers that other tests do not:
  - modules/config.yaml manifest with explicit class mappings (missing_class)
  - contracts/ package with cross-file imports (ModuleNotFoundError on sentinels)
  - double-loading guard (all contracts are discovered even when only zip is used)
"""

import shutil
from pathlib import Path

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigNode, GraphConfigSrcPort
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph
from rtl_comrade.loader_plugin import load_plugin_config

_PROJECT_ROOT = Path(__file__).parents[2]


def _copy_plugins(tmp_path):
	shutil.copytree(
		_PROJECT_ROOT / "modules",
		tmp_path / "modules",
		ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"),
	)
	shutil.copytree(
		_PROJECT_ROOT / "contracts",
		tmp_path / "contracts",
		ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
	)


def test_real_plugins_load_and_run(logging_handler, tmp_path):
	"""Graph equivalent to graph2.yaml using real plugin source trees."""
	_copy_plugins(tmp_path)

	(tmp_path / "file1.txt").write_text("1\n2\n3\n")
	(tmp_path / "file2.txt").write_text("10\n20\n30\n")

	config = GraphConfig(
		modules=load_plugin_config(tmp_path / "modules"),
		contracts=load_plugin_config(tmp_path / "contracts"),
		nodes=[
			GraphConfigNode(id="file-1", module="fileread", config={"file": str(tmp_path / "file1.txt")}, contract="zip", contract_config={}),
			GraphConfigNode(id="file-2", module="fileread", config={"file": str(tmp_path / "file2.txt")}, contract="zip", contract_config={}),
			GraphConfigNode(id="add",    module="add",      config={},                                    contract="zip", contract_config={}),
			GraphConfigNode(id="output", module="stdout",   config={},                                    contract="zip", contract_config={}),
		],
		edges=[
			GraphConfigEdge(src=GraphConfigSrcPort(node="file-1", port="default"), dst=GraphConfigDstPort(node="add",    port=1)),
			GraphConfigEdge(src=GraphConfigSrcPort(node="file-2", port="default"), dst=GraphConfigDstPort(node="add",    port=2)),
			GraphConfigEdge(src=GraphConfigSrcPort(node="add",    port="default"), dst=GraphConfigDstPort(node="output", port=1)),
		],
	)

	Graph.construct_run(config, lambda p, h, d: None, lambda: None)()
	assert not logging_handler.failure
