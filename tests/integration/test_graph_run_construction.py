"""Integration tests: graph construction — config → GraphConfig → Graph assembly and CLI-source dedup/override."""

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigNode, GraphConfigNodePlugin, GraphConfigSrcCLI, GraphConfigSrcPort, GraphFileConfig
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph

from tests.integration.graph_run_common import SIDE_CHANNEL, _node, _write_plugin
from tests.integration.graph_run_common import reset_side_channel  # noqa: F401  # pylint: disable=unused-import


def test_it11_from_file_valid(logging_handler, tmp_path):
	module_file = tmp_path / "mods.py"
	module_file.write_text("class Src:\n    def run(self):\n        return 1\n")

	graph_yaml = tmp_path / "graph.yaml"
	graph_yaml.write_text(f"modules:\n- {module_file}\nnodes:\n- id: src\n  module: src\nedges: []\n")

	graph = Graph.from_config(GraphConfig.from_file(graph_yaml))
	assert isinstance(graph, Graph)
	assert "src" in graph.nodes


def test_it19_cli_fanout_across_edges(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Collect:
            def run(self, x):
                import tests.integration.graph_run_common as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

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
				src=GraphConfigSrcCLI(cli="value", type="int"),
				dst=GraphConfigDstPort(node="collect2", port=1),
			),
		],
		modules=[tmp_path / "mods.py"],
	)
	graph_config = GraphConfig.from_file_config(config)
	assert list(graph_config.sig.parameters) == ["value"]  # deduped to a single param
	assert [name for name, _ in graph_config.cli_srcs] == ["cli-value", "cli-value"]  # but one src per destination
	Graph.construct_run(graph_config, lambda p, h, d: None, lambda: None)(value=7)
	assert sorted(SIDE_CHANNEL) == [7, 7]  # the one value reached both nodes
	assert logging_handler.failure is False


def test_it21_cli_config_module(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        from dataclasses import dataclass
        from serde import serde

        class Src:
            @serde
            @dataclass
            class Config:
                value: int

            def __init__(self, config):
                self.config = config

            def run(self):
                import tests.integration.graph_run_common as t
                t.SIDE_CHANNEL.append(self.config.value)
                return None
    """,
	)

	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="src",
				module=GraphConfigNodePlugin(name="src", cli={"value": GraphConfigSrcCLI(cli="val", type="int")}),
			)
		],
		edges=[],
		modules=[tmp_path / "mods.py"],
	)
	graph_config = GraphConfig.from_file_config(config)
	assert "val" in graph_config.sig.parameters
	Graph.construct_run(graph_config, lambda p, h, d: None, lambda: None)(val=42)
	assert SIDE_CHANNEL == [42]
	assert logging_handler.failure is False


def test_it22_cli_contract_config(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Src:
            def run(self):
                yield 1
                yield 2

        class Collect:
            def run(self, x):
                import tests.integration.graph_run_common as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)
	_write_plugin(
		tmp_path,
		"contracts.py",
		"""\
        from dataclasses import dataclass, field as dc_field
        from serde import serde

        class Persist:
            @serde
            @dataclass
            class Config:
                limit: int = 0

            def __init__(self, id, ports, config):
                self.id = id
                self.ports = ports
                self.limit = config.limit
                self._count = 0

            async def get_inputs(self):
                from rtl_comrade.api import EndSentinel
                if self._count >= self.limit:
                    return EndSentinel(self.id)
                self._count += 1
                return {name: await port.get() for name, port in self.ports.items()}
    """,
	)

	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(id="src", module=GraphConfigNodePlugin(name="src")),
			GraphConfigNode(
				id="collect",
				module=GraphConfigNodePlugin(name="collect"),
				contract=GraphConfigNodePlugin(name="persist", cli={"limit": GraphConfigSrcCLI(cli="n", type="int")}),
			),
		],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcPort(node="src"),
				dst=GraphConfigDstPort(node="collect", port=1),
			)
		],
		modules=[tmp_path / "mods.py"],
		contracts=[tmp_path / "contracts.py"],
	)
	graph_config = GraphConfig.from_file_config(config)
	assert "n" in graph_config.sig.parameters
	Graph.construct_run(graph_config, lambda p, h, d: None, lambda: None)(n=1)
	assert len(SIDE_CHANNEL) == 1
	assert logging_handler.failure is False


def test_it23_cli_config_overrides_static(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        from dataclasses import dataclass
        from serde import serde

        class Src:
            @serde
            @dataclass
            class Config:
                value: int

            def __init__(self, config):
                self.config = config

            def run(self):
                import tests.integration.graph_run_common as t
                t.SIDE_CHANNEL.append(self.config.value)
                return None
    """,
	)

	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="src",
				module=GraphConfigNodePlugin(name="src", config={"value": 0}, cli={"value": GraphConfigSrcCLI(cli="val", type="int")}),
			)
		],
		edges=[],
		modules=[tmp_path / "mods.py"],
	)
	graph_config = GraphConfig.from_file_config(config)
	Graph.construct_run(graph_config, lambda p, h, d: None, lambda: None)(val=99)
	assert SIDE_CHANNEL == [99]


def test_it25_identical_cli_across_edge_and_config_dedups(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="collect",
				module=GraphConfigNodePlugin(name="m", cli={"field": GraphConfigSrcCLI(cli="value")}),
			)
		],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value"),
				dst=GraphConfigDstPort(node="collect", port=1),
			)
		],
	)
	graph_config = GraphConfig.from_file_config(config)
	assert list(graph_config.sig.parameters) == ["value"]
	assert logging_handler.failure is False


def test_it26_identical_cli_across_nodes_dedups(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="n1",
				module=GraphConfigNodePlugin(name="m", cli={"field": GraphConfigSrcCLI(cli="value")}),
			),
			GraphConfigNode(
				id="n2",
				module=GraphConfigNodePlugin(name="m", cli={"field": GraphConfigSrcCLI(cli="value")}),
			),
		],
		edges=[],
	)
	graph_config = GraphConfig.from_file_config(config)
	assert list(graph_config.sig.parameters) == ["value"]
	assert logging_handler.failure is False


def test_it29_identical_cli_across_contract_configs_dedups(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="n1",
				module=GraphConfigNodePlugin(name="m"),
				contract=GraphConfigNodePlugin(cli={"limit": GraphConfigSrcCLI(cli="n")}),
			),
			GraphConfigNode(
				id="n2",
				module=GraphConfigNodePlugin(name="m"),
				contract=GraphConfigNodePlugin(cli={"limit": GraphConfigSrcCLI(cli="n")}),
			),
		],
		edges=[],
	)
	graph_config = GraphConfig.from_file_config(config)
	assert list(graph_config.sig.parameters) == ["n"]
	assert logging_handler.failure is False


def test_it30_cli_contract_config_overrides_static(logging_handler):
	config = GraphFileConfig(
		nodes=[
			GraphConfigNode(
				id="n1",
				module=GraphConfigNodePlugin(name="m"),
				contract=GraphConfigNodePlugin(config={"limit": 0}, cli={"limit": GraphConfigSrcCLI(cli="n", type="int")}),
			)
		],
		edges=[],
	)
	graph_config = GraphConfig.from_file_config(config)
	assert "n" in graph_config.sig.parameters
	assert logging_handler.failure is False
