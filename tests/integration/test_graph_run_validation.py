"""Integration tests: graph validation — malformed/inconsistent config is rejected with typer.Exit."""

import pytest
import typer

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigNode, GraphConfigSrcCLI, GraphFileConfig
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph

from tests.integration.graph_run_common import _node, _write_plugin


def test_it12_from_file_not_found(logging_handler):
	with pytest.raises(typer.Exit):
		GraphConfig.from_file("/no/such/graph.yaml")


def test_it13_from_file_malformed(logging_handler, tmp_path):
	bad = tmp_path / "bad.yaml"
	bad.write_text("nodes: [\nunclosed\n")
	with pytest.raises(typer.Exit):
		GraphConfig.from_file(str(bad))


def test_it18_blank_cli_name(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Collect:
            def run(self, x):
                return None
    """,
	)

	config = GraphFileConfig(
		nodes=[_node("collect", "collect")],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli=""),
				dst=GraphConfigDstPort(node="collect", port=1),
			)
		],
		modules=[tmp_path / "mods.py"],
	)
	with pytest.raises(typer.Exit):
		Graph.from_config(GraphConfig.from_file_config(config))  # IT-18


def test_it19b_mismatched_cli_across_edges(logging_handler):
	config = GraphFileConfig(
		nodes=[
			_node("collect1", "collect"),
			_node("collect2", "collect"),
		],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value", type="int"),
				dst=GraphConfigDstPort(node="collect1", port=1),
			),
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value", type="str"),
				dst=GraphConfigDstPort(node="collect2", port=1),
			),
		],
	)
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(config)


def test_it24_blank_cli_name_in_cli_config(logging_handler, tmp_path):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="n1",
				module="m",
				cli_config={"field": GraphConfigSrcCLI(cli="")},
			)
		],
		edges=[],
	)
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(config)


def test_it25b_mismatched_cli_across_edge_and_config(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="collect",
				module="m",
				cli_config={"field": GraphConfigSrcCLI(cli="value", default=5)},
			)
		],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value"),
				dst=GraphConfigDstPort(node="collect", port=1),
			)
		],
	)
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(config)


def test_it26b_mismatched_cli_across_nodes(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="n1",
				module="m",
				cli_config={"field": GraphConfigSrcCLI(cli="value")},
			),
			GraphConfigNode(
				id="n2",
				module="m",
				cli_config={"field": GraphConfigSrcCLI(cli="value", default=5)},
			),
		],
		edges=[],
	)
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(config)


def test_it28_blank_cli_name_in_cli_contract_config(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="n1",
				module="m",
				cli_contract_config={"limit": GraphConfigSrcCLI(cli="")},
			)
		],
		edges=[],
	)
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(config)


def test_it29b_mismatched_cli_across_contract_configs(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="n1",
				module="m",
				cli_contract_config={"limit": GraphConfigSrcCLI(cli="n")},
			),
			GraphConfigNode(
				id="n2",
				module="m",
				cli_contract_config={"limit": GraphConfigSrcCLI(cli="n", default=5)},
			),
		],
		edges=[],
	)
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(config)
