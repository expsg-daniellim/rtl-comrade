"""Integration tests: graph execution (Graph.construct_run) — data flow, contracts, runtime failure semantics."""

import pytest
import typer

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigSrcCLI, GraphConfigSrcPort, GraphFileConfig
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph

from tests.integration.graph_run_common import SIDE_CHANNEL, _edge, _node, _pfc, _run_graph, _write_plugin
from tests.integration.graph_run_common import reset_side_channel  # noqa: F401  # pylint: disable=unused-import


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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
                t.SIDE_CHANNEL.append(('odd', x))
                return None

        class CollectEven:
            def run(self, x):
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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
	with pytest.raises(typer.Exit):
		_run_graph(config)


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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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
                import tests.integration.graph_run_common as t
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


def test_it16_cli_option(logging_handler, tmp_path):
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
		nodes=[_node("collect", "collect")],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcCLI(cli="value", type="int"),
				dst=GraphConfigDstPort(node="collect", port=1),
			)
		],
		modules=[tmp_path / "mods.py"],
	)
	graph_config = GraphConfig.from_file_config(config)
	Graph.construct_run(graph_config, lambda p, h, d: None, lambda: None)(value=99)
	assert SIDE_CHANNEL == [99]
	assert logging_handler.failure is False


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
		modules=[tmp_path / "mods.py"],
	)
	graph_config = GraphConfig.from_file_config(config)
	Graph.construct_run(graph_config, lambda p, h, d: None, lambda: None)()  # 'value' kwarg absent
	assert logging_handler.failure is True


def test_it20_node_fatal_propagates(logging_handler, tmp_path):
	_write_plugin(tmp_path, "mods.py", """\
        import structlog
        log = structlog.get_logger()

        class Crasher:
            def run(self):
                log.fatal('crash')
    """)
	config = GraphConfig(
		nodes=[_node("crasher", "crasher")],
		edges=[],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	cleanup_called = []
	with pytest.raises(typer.Exit):
		Graph.construct_run(config, lambda p, h, d: None, lambda: cleanup_called.append(True))()
	assert not cleanup_called


def test_it27_required_default_input(logging_handler, tmp_path):
	# "combine" has b=99 default, but its edge marks b required, so the node awaits a
	# real value on b instead of running with the default. Exercises the full
	# config → graph → Node → ContractPort path for both index- and name-addressed dsts.
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        class SrcA:
            def run(self):
                yield 1
                yield 2
                yield 3

        class SrcB:
            def run(self):
                yield 10
                yield 20
                yield 30

        class Combine:
            def run(self, a, b=99):
                import tests.integration.graph_run_common as t
                t.SIDE_CHANNEL.append(a + b)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("src_a", "src_a"),
			_node("src_b", "src_b"),
			_node("combine", "combine"),
		],
		edges=[
			GraphConfigEdge(
				src=GraphConfigSrcPort(node="src_a"),
				dst=GraphConfigDstPort(node="combine", port=1),  # index-addressed
			),
			GraphConfigEdge(
				src=GraphConfigSrcPort(node="src_b"),
				dst=GraphConfigDstPort(node="combine", port="b", required=True),  # name-addressed
			),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert SIDE_CHANNEL == [11, 22, 33]
	assert logging_handler.failure is False


def test_it28_exclusive_arms_converge_on_one_port(logging_handler, tmp_path):
	# The two arms rejoin on collect.x through separate nodes, one of them slow enough to still be
	# working when the other has already ended, so the merged port must outlive its first EndSentinel.
	_write_plugin(
		tmp_path,
		"mods.py",
		"""\
        import asyncio

        class Gen:
            def run(self):
                yield 1
                yield 2
                yield 3
                yield 4

        class Router:
            def run(self, x):
                if x % 2 == 0:
                    yield ("even", x)
                else:
                    yield ("odd", x)

        class Slow:
            async def run(self, x):
                await asyncio.sleep(0.05)
                return x

        class Fast:
            def run(self, x):
                return x

        class Collect:
            def run(self, x):
                import tests.integration.graph_run_common as t
                t.SIDE_CHANNEL.append(x)
                return None
    """,
	)

	config = GraphConfig(
		nodes=[
			_node("gen", "gen"),
			_node("router", "router"),
			_node("slow", "slow"),
			_node("fast", "fast"),
			_node("collect", "collect"),
		],
		edges=[
			_edge("gen", "router"),
			_edge("router", "slow", src_port="even"),
			_edge("router", "fast", src_port="odd"),
			_edge("slow", "collect"),
			_edge("fast", "collect"),
		],
		modules=[_pfc(tmp_path / "mods.py")],
		contracts=[],
	)
	_run_graph(config)
	assert sorted(SIDE_CHANNEL) == [1, 2, 3, 4]
	assert logging_handler.failure is False
