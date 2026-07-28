"""Shared helpers and fixtures for the graph-run integration tests.

Split across test_graph_run_runtime.py (execution), test_graph_run_construction.py
(assembly / config → graph), and test_graph_run_validation.py (rejection of bad config).
Inline plugin sources reach back for SIDE_CHANNEL via ``import tests.integration.graph_run_common as t``.
"""

import textwrap
from pathlib import Path

import pytest

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigNode, GraphConfigNodePlugin, GraphConfigSrcPort
from rtl_comrade.graph import Graph
from rtl_comrade.loader_plugin import PluginFileConfig

SIDE_CHANNEL: list = []


def _pfc(path) -> PluginFileConfig:
	return PluginFileConfig(name=None, file=Path(path), type_=None, plugins=None)


def _node(id_, module, config=None, contract="", contract_config=None):
	return GraphConfigNode(
		id=id_,
		module=GraphConfigNodePlugin(name=module, config=config or {}),
		contract=GraphConfigNodePlugin(name=contract, config=contract_config or {}),
	)


def _edge(src_node, dst_node, src_port="default", dst_port=1):
	return GraphConfigEdge(
		src=GraphConfigSrcPort(node=src_node, port=src_port),
		dst=GraphConfigDstPort(node=dst_node, port=dst_port),
	)


def _write_plugin(tmp_path, name, src):
	f = tmp_path / name
	f.write_text(textwrap.dedent(src))
	return f


def _run_graph(config):
	Graph.construct_run(config, lambda p, h, d: None, lambda: None)()


@pytest.fixture(autouse=True)
def reset_side_channel():
	SIDE_CHANNEL.clear()
	yield
	SIDE_CHANNEL.clear()
