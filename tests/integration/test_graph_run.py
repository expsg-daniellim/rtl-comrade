"""Integration tests: full Graph.from_config → Graph.run path."""

import textwrap
from pathlib import Path

import pytest

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigNode, GraphConfigSrcCLI, GraphConfigSrcPort, GraphFileConfig
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph
from rtl_comrade.loader import PluginFileConfig


def _pfc(path) -> PluginFileConfig:
	return PluginFileConfig(name=None, file=Path(path), type_=None, plugins=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIDE_CHANNEL: list = []


def _node(id_, module, config=None, contract="", contract_config=None):
	return GraphConfigNode(
		id=id_,
		module=module,
		config=config or {},
		contract=contract,
		contract_config=contract_config or {},
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
	Graph.construct_run(config, lambda: None)()


@pytest.fixture(autouse=True)
def reset_side_channel():
	SIDE_CHANNEL.clear()
	yield
	SIDE_CHANNEL.clear()


# ---------------------------------------------------------------------------
# IT-1: Linear source → transform → sink
# ---------------------------------------------------------------------------


def test_it1_linear(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        SIDE_CHANNEL = None  # injected at runtime

        class Gen:
            def run(self):
                yield 1
                yield 2
                yield 3

        class Double:
            def run(self, x):
                return x * 2

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("gen", "gen"),
			_node("double", "double"),
			_node("collect", "collect"),
		],
		edges=[
			_edge("gen", "double"),
			_edge("double", "collect"),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == [2, 4, 6]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-2: Fan-in (zip contract)
# ---------------------------------------------------------------------------


def test_it2_fan_in(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class SrcA:
            def run(self):
                yield 1
                yield 2

        class SrcB:
            def run(self):
                yield 10
                yield 20

        class Add:
            def run(self, a, b):
                return a + b

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)
	_write_plugin(
		tmp_path,
		"contracts.py",
		"""\
        from dataclasses import dataclass

        @dataclass
        class Zip:
            id: str
            ports: dict

            async def get_inputs(self):
                from rtl_comrade.api import EndSentinel
                res = {name: await port.get() for name, port in self.ports.items()}
                if any(isinstance(v, EndSentinel) for v in res.values()):
                    return EndSentinel(self.id)
                return res
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("src_a", "src_a"),
			_node("src_b", "src_b"),
			_node("add", "add", contract="zip"),
			_node("collect", "collect"),
		],
		edges=[
			_edge("src_a", "add", dst_port=1),
			_edge("src_b", "add", dst_port=2),
			_edge("add", "collect"),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[_pfc(tmp_path / "contracts.py")],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == [11, 22]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-3: EndSentinel propagation across two hops
# ---------------------------------------------------------------------------


def test_it3_sentinel_propagation(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Gen:
            def run(self):
                yield 'a'
                yield 'b'
                yield 'c'

        class Passthrough:
            def run(self, x):
                return x

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("gen", "gen"),
			_node("pt", "passthrough"),
			_node("collect", "collect"),
		],
		edges=[
			_edge("gen", "pt"),
			_edge("pt", "collect"),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == ["a", "b", "c"]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-4: Source-only node (no inputs) runs once
# ---------------------------------------------------------------------------


def test_it4_source_only_runs_once(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Counter:
            def run(self):
                return 'once'

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("counter", "counter"),
			_node("collect", "collect"),
		],
		edges=[_edge("counter", "collect")],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert len(SIDE_CHANNEL) == 1
	assert SIDE_CHANNEL[0] == "once"
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-5: Default input port
# ---------------------------------------------------------------------------


def test_it5_default_input(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Src:
            def run(self):
                return 5

        class Adder:
            def run(self, a, b=10):
                return a + b

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("src", "src"),
			_node("adder", "adder"),
			_node("collect", "collect"),
		],
		edges=[
			_edge("src", "adder", dst_port=1),
			_edge("adder", "collect"),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == [15]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-6: Persistent input
# ---------------------------------------------------------------------------


def test_it6_persistent_input(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Src:
            def run(self):
                yield 1
                yield 2
                yield 3

        class MulSrc:
            def run(self):
                return 5

        class Accumulate:
            def run(self, value, multiplier):
                return value * multiplier

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("src", "src"),
			_node("mul_src", "mul_src"),
			_node(
				"accumulate",
				"accumulate",
				contract_config={"persistent_inputs": ["multiplier"]},
			),
			_node("collect", "collect"),
		],
		edges=[
			_edge("src", "accumulate", dst_port=1),
			_edge("mul_src", "accumulate", dst_port=2),
			_edge("accumulate", "collect"),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == [5, 10, 15]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-7: Named output port routing
# ---------------------------------------------------------------------------


def test_it7_named_port_routing(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Router:
            def run(self):
                yield ('odd', 1)
                yield ('even', 2)
                yield ('odd', 3)
                yield ('even', 4)

        class CollectOdd:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(('odd', x))
                return None

        class CollectEven:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(('even', x))
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("router", "router"),
			_node("collect_odd", "collect_odd"),
			_node("collect_even", "collect_even"),
		],
		edges=[
			_edge("router", "collect_odd", src_port="odd"),
			_edge("router", "collect_even", src_port="even"),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	odd_vals = [v for tag, v in SIDE_CHANNEL if tag == "odd"]
	even_vals = [v for tag, v in SIDE_CHANNEL if tag == "even"]
	assert odd_vals == [1, 3]
	assert even_vals == [2, 4]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-8: Async module
# ---------------------------------------------------------------------------


def test_it8_async_module(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class AsyncGen:
            async def run(self):
                yield 10
                yield 20
                yield 30

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("async_gen", "async_gen"),
			_node("collect", "collect"),
		],
		edges=[_edge("async_gen", "collect")],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == [10, 20, 30]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-9: Module raises exception
# ---------------------------------------------------------------------------


def test_it9_module_exception(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Crasher:
            def run(self):
                raise ValueError('boom')

        class Collect:
            def run(self, x):
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("crasher", "crasher"),
			_node("collect", "collect"),
		],
		edges=[_edge("crasher", "collect")],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	with pytest.raises(SystemExit):
		_run_graph(config)


# ---------------------------------------------------------------------------
# IT-10: Module logs ERROR (deferred failure)
# ---------------------------------------------------------------------------


def test_it10_module_error_deferred(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        import structlog
        log = structlog.get_logger()

        class Errorer:
            def run(self):
                log.error('test_error_event')
                return 'still_here'

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("errorer", "errorer"),
			_node("collect", "collect"),
		],
		edges=[_edge("errorer", "collect")],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == ["still_here"]
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# IT-11: Graph.from_file — valid YAML
# ---------------------------------------------------------------------------


def test_it11_from_file_valid(logging_handler, tmp_path):
	module_file = tmp_path / "mods.py"
	module_file.write_text("class Src:\n    def run(self):\n        return 1\n")

	graph_yaml = tmp_path / "graph.yaml"
	graph_yaml.write_text(f"modules:\n- {module_file}\nnodes:\n- id: src\n  module: src\nedges: []\n")

	graph = Graph.from_config(GraphConfig.from_file(str(graph_yaml)))
	assert isinstance(graph, Graph)
	assert "src" in graph.nodes


# ---------------------------------------------------------------------------
# IT-12: Graph.from_file — file not found
# ---------------------------------------------------------------------------


def test_it12_from_file_not_found(logging_handler):
	with pytest.raises(SystemExit):
		GraphConfig.from_file("/no/such/graph.yaml")


# ---------------------------------------------------------------------------
# IT-13: GraphConfig.from_file — malformed YAML
# ---------------------------------------------------------------------------


def test_it13_from_file_malformed(logging_handler, tmp_path):
	bad = tmp_path / "bad.yaml"
	bad.write_text("nodes: [\nunclosed\n")
	with pytest.raises(SystemExit):
		GraphConfig.from_file(str(bad))


# ---------------------------------------------------------------------------
# IT-14: Destination port addressed by 1-based index
# ---------------------------------------------------------------------------


def test_it14_dst_port_by_index(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Src:
            def run(self):
                return 7

        class Sink:
            def run(self, first, second):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(second)
                return None

        class Fill:
            def run(self):
                return 0
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("src", "src"),
			_node("fill", "fill"),
			_node("sink", "sink"),
		],
		edges=[
			_edge("src", "sink", dst_port=2),  # integer index
			_edge("fill", "sink", dst_port=1),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert 7 in SIDE_CHANNEL
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-15: non_definite_emits warning does not block execution
# ---------------------------------------------------------------------------


def test_it15_non_definite_emits(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class DynSrc:
            def run(self):
                port = 'default'
                return (port, 42)

        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("dyn_src", "dyn_src"),
			_node("collect", "collect"),
		],
		edges=[_edge("dyn_src", "collect")],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == [42]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-16: CLI option value flows through to node
# ---------------------------------------------------------------------------


def test_it16_cli_option(logging_handler, tmp_path):
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class Collect:
            def run(self, x):
                import tests.integration.test_graph_run as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphFileConfig(
		nodes=[_node("collect", "collect")],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value", type="int"),
				dst=GraphConfigDstPort(node="collect", port=1),
			)
		],
		modules=[str(tmp_path / "mods.py")],
	)
	graph_config = GraphConfig.from_file_config(config)
	Graph.construct_run(graph_config, lambda: None)(value=99)
	assert SIDE_CHANNEL == [99]
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# IT-17: Missing CLI kwarg logs error and sets failure flag
# ---------------------------------------------------------------------------


def test_it17_missing_cli_kwarg(logging_handler, tmp_path):
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
				src=GraphConfigSrcCLI(cli="value"),
				dst=GraphConfigDstPort(node="collect", port=1),
			)
		],
		modules=[str(tmp_path / "mods.py")],
	)
	graph_config = GraphConfig.from_file_config(config)
	Graph.construct_run(graph_config, lambda: None)()  # 'value' kwarg absent
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# IT-18: Blank CLI name causes fatal error during graph construction
# ---------------------------------------------------------------------------


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
		modules=[str(tmp_path / "mods.py")],
	)
	with pytest.raises(SystemExit):
		Graph.from_config(GraphConfig.from_file_config(config))


# ---------------------------------------------------------------------------
# IT-19: Duplicate CLI name causes fatal error during graph construction
# ---------------------------------------------------------------------------


def test_it19_duplicate_cli_name(logging_handler, tmp_path):
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
		nodes=[
			_node("collect1", "collect"),
			_node("collect2", "collect"),
		],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value"),
				dst=GraphConfigDstPort(node="collect1", port=1),
			),
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value"),
				dst=GraphConfigDstPort(node="collect2", port=1),
			),
		],
		modules=[str(tmp_path / "mods.py")],
	)
	with pytest.raises(SystemExit):
		Graph.from_config(GraphConfig.from_file_config(config))
