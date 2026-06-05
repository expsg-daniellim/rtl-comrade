"""Unit tests for graph.py — Graph.from_config validation."""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigNode, GraphConfigSrcCLI, GraphConfigSrcPort, GraphFileConfig
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.graph import Graph


# ---------------------------------------------------------------------------
# Inline module/contract classes (must be at module scope for inspect.getsource)
# ---------------------------------------------------------------------------


class _SourceModule:
	def run(self):
		return 1


class _SinkModule:
	def run(self, a):
		return None


class _TwoInputModule:
	def run(self, a, b):
		return None


class _NamedEmitModule:
	def run(self):
		return ("out", 1)


class _DynamicEmitModule:
	def run(self):
		port = "default"
		return (port, 1)


class _BasicContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	async def get_inputs(self):
		from rtl_comrade.api import EndSentinel  # pylint: disable=import-outside-toplevel

		return EndSentinel(self.id)


class _CycleModule:
	"""Module with one input and one output, needed for valid cycle/no-source graphs."""

	def run(self, a):
		return a


class _YieldFromModule:
	def run(self):
		yield from [1, 2, 3]


class _KwargsModule:
	def run(self, **kwargs):
		return 1


# Mapping helpers
_MODULE_MAP = {
	"source_mod": _SourceModule,
	"sink_mod": _SinkModule,
	"two_input_mod": _TwoInputModule,
	"named_emit_mod": _NamedEmitModule,
	"dynamic_emit_mod": _DynamicEmitModule,
}
_CONTRACT_MAP = {
	"basic_contract": _BasicContract,
}


def _node(id_, module, contract=""):
	return GraphConfigNode(id=id_, module=module, contract=contract)


def _edge(src_node, src_port, dst_node, dst_port):
	return GraphConfigEdge(
		src=GraphConfigSrcPort(node=src_node, port=src_port),
		dst=GraphConfigDstPort(node=dst_node, port=dst_port),
	)


def _make_config(nodes, edges):
	return GraphConfig(nodes=nodes, edges=edges, modules=[], contracts=[])


def _from_config(config):
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		if call_count[0] == 1:
			return _MODULE_MAP
		return {}  # contract load returns empty

	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		return Graph.from_config(config)


def _from_config_with_contracts(config):
	"""Load with both module and contract mappings."""
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		if call_count[0] == 1:
			return _MODULE_MAP
		return _CONTRACT_MAP

	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		return Graph.from_config(config)


# --- Node construction errors ---


def test_invalid_module_fatal(logging_handler):
	config = _make_config([_node("n1", "nonexistent_mod")], [])
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_invalid_contract_fatal(logging_handler):
	config = _make_config([_node("n1", "source_mod", contract="nonexistent_contract")], [])
	with pytest.raises(typer.Exit):
		_from_config_with_contracts(config)


def test_duplicate_node_id_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(GraphFileConfig(
			nodes=[GraphConfigNode(id="n1", module="source_mod"), GraphConfigNode(id="n1", module="sink_mod")],
			edges=[],
		))


def test_from_file_config_stores_relative_path(logging_handler, tmp_path):
	result = GraphConfig.from_file_config(GraphFileConfig(nodes=[], edges=[]), relative_path=tmp_path)
	assert result.relative_path == tmp_path


def test_from_file_config_default_relative_path_is_empty_path(logging_handler):
	result = GraphConfig.from_file_config(GraphFileConfig(nodes=[], edges=[]))
	assert result.relative_path == Path()


# --- Edge construction errors ---


def test_invalid_dst_node_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(GraphFileConfig(
			nodes=[GraphConfigNode(id="src", module="source_mod")],
			edges=[GraphConfigEdge(src=GraphConfigSrcPort(node="src"), dst=GraphConfigDstPort(node="nonexistent"))],
		))


def test_invalid_dst_port_fatal(logging_handler):
	config = _make_config(
		[_node("src", "source_mod"), _node("sink", "sink_mod")],
		[_edge("src", "default", "sink", "nonexistent_port")],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_invalid_src_port_fatal(logging_handler):
	config = _make_config(
		[_node("src", "source_mod"), _node("sink", "sink_mod")],
		[_edge("src", "nonexistent_emit", "sink", 1)],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_overloaded_srcs_fatal(logging_handler):
	config = _make_config(
		[
			_node("src1", "source_mod"),
			_node("src2", "source_mod"),
			_node("sink", "sink_mod"),
		],
		[
			_edge("src1", "default", "sink", 1),
			_edge("src2", "default", "sink", 1),
		],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


# --- Edge warnings ---


def test_unused_edge_warns(logging_handler):
	class _DefaultSinkMod:
		def run(self, a=0):
			return None

	module_map = {**_MODULE_MAP, "default_sink": _DefaultSinkMod}
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return module_map if call_count[0] == 1 else {}

	graph_config = GraphConfig.from_file_config(GraphFileConfig(
		nodes=[GraphConfigNode(id="sink", module="default_sink")],
		edges=[GraphConfigEdge(src=GraphConfigSrcPort(node="nonexistent_src"), dst=GraphConfigDstPort(node="sink"))],
	))
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		graph = Graph.from_config(graph_config)
	assert "sink" in graph.nodes


# --- Graph-level structural validation ---


def test_cyclic_graph_fatal(logging_handler):
	config = _make_config(
		[_node("a", "sink_mod"), _node("b", "sink_mod")],
		[
			_edge("a", "default", "b", 1),
			_edge("b", "default", "a", 1),
		],
	)
	# Both nodes have required inputs; will fail deadlock check too.
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_required_input_no_edge_fatal(logging_handler):
	config = _make_config(
		[_node("src", "source_mod"), _node("sink", "sink_mod")],
		[],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_no_source_capable_node_fatal(logging_handler):
	config = _make_config(
		[_node("a", "sink_mod"), _node("b", "sink_mod")],
		[_edge("a", "default", "b", 1)],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


# --- Happy paths ---


def test_minimal_one_node_graph(logging_handler):
	config = _make_config([_node("src", "source_mod")], [])
	graph = _from_config(config)
	assert "src" in graph.nodes


def test_two_node_graph(logging_handler):
	config = _make_config(
		[_node("src", "source_mod"), _node("sink", "sink_mod")],
		[_edge("src", "default", "sink", 1)],
	)
	graph = _from_config(config)
	assert "src" in graph.nodes
	assert "sink" in graph.nodes
	src_node = graph.nodes["src"]
	assert len(src_node.dsts) == 1
	assert src_node.dsts[0].other_node.id == "sink"


def test_dst_port_by_index_resolves(logging_handler):
	class _SourceMod2:
		def run(self):
			return 1

	module_map = {**_MODULE_MAP, "source_mod2": _SourceMod2}
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return module_map if call_count[0] == 1 else {}

	config = _make_config(
		[
			_node("src", "source_mod"),
			_node("src2", "source_mod2"),
			_node("sink", "two_input_mod"),
		],
		[_edge("src", "default", "sink", 2), _edge("src2", "default", "sink", 1)],
	)
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		graph = Graph.from_config(config)
	src_node = graph.nodes["src"]
	assert src_node.dsts is not None
	assert src_node.dsts[0].other_port == "b"


def test_non_definite_emits_warns(logging_handler):
	config = _make_config(
		[_node("src", "dynamic_emit_mod"), _node("sink", "sink_mod")],
		[_edge("src", "someport", "sink", 1)],
	)
	# dynamic emit → non_definite_emits warn, not fatal
	graph = _from_config(config)
	assert "src" in graph.nodes
	assert logging_handler.failure is False


def test_yield_from_non_definite_emits_warns(logging_handler):
	module_map = {**_MODULE_MAP, "yield_from_mod": _YieldFromModule}
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return module_map if call_count[0] == 1 else {}

	config = _make_config(
		[_node("src", "yield_from_mod"), _node("sink", "sink_mod")],
		[_edge("src", "someport", "sink", 1)],
	)
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		graph = Graph.from_config(config)
	assert "src" in graph.nodes
	assert logging_handler.failure is False


def test_non_definite_inputs_warns(logging_handler):
	module_map = {**_MODULE_MAP, "kwargs_mod": _KwargsModule}
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return module_map if call_count[0] == 1 else {}

	config = _make_config(
		[_node("src", "kwargs_mod"), _node("sink", "sink_mod")],
		[_edge("src", "default", "sink", 1)],
	)
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		graph = Graph.from_config(config)
	assert "src" in graph.nodes
	assert logging_handler.failure is False


def test_non_definite_inputs_allows_undeclared_dst_port(logging_handler):
	module_map = {**_MODULE_MAP, "kwargs_mod": _KwargsModule}
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return module_map if call_count[0] == 1 else {}

	# "any_port" is not declared on kwargs_mod — should be allowed without error
	config = _make_config(
		[_node("src", "source_mod"), _node("agg", "kwargs_mod")],
		[_edge("src", "default", "agg", "any_port")],
	)
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		graph = Graph.from_config(config)
	assert "agg" in graph.nodes
	assert logging_handler.failure is False
	assert graph.nodes["src"].dsts[0].other_port == "any_port"


# --- Plugin validation ---


def test_module_plugin_missing_run_raises(logging_handler):
	# A module without a run attribute causes ModuleStructure to raise AttributeError
	# (inspect.signature(Module.run) fails) before the missing_runs guard is reached.
	class _NoRunModule:
		pass

	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return {"no_run_mod": _NoRunModule} if call_count[0] == 1 else {}

	config = _make_config([_node("n1", "no_run_mod")], [])
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		with pytest.raises(AttributeError):
			Graph.from_config(config)


def test_contract_plugin_missing_get_inputs_fatal(logging_handler):
	class _NoGetInputsContract:
		def __init__(self, id, ports):  # pylint: disable=redefined-builtin
			pass

	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return _MODULE_MAP if call_count[0] == 1 else {"bad_contract": _NoGetInputsContract}

	config = _make_config([_node("n1", "source_mod", contract="bad_contract")], [])
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		with pytest.raises(typer.Exit):
			Graph.from_config(config)


# --- Graph-level structural validation (using _CycleModule for valid edges) ---


def test_cyclic_graph_detected_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(GraphFileConfig(
			nodes=[GraphConfigNode(id="a", module="m"), GraphConfigNode(id="b", module="m")],
			edges=[
				GraphConfigEdge(src=GraphConfigSrcPort(node="a"), dst=GraphConfigDstPort(node="b")),
				GraphConfigEdge(src=GraphConfigSrcPort(node="b"), dst=GraphConfigDstPort(node="a")),
			],
		))


# --- CLI edge errors ---


def test_cli_name_conflicts_with_node_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(GraphFileConfig(
			nodes=[GraphConfigNode(id="cli-foo", module="m")],
			edges=[GraphConfigEdge(src=GraphConfigSrcCLI(cli="foo"), dst=GraphConfigDstPort(node="cli-foo"))],
		))


def test_cli_invalid_parameter_name_fatal(logging_handler, tmp_path):
	(tmp_path / 'graph.yaml').write_text(
		'nodes: []\n'
		'edges:\n'
		'  - src:\n'
		'      cli: invalid-name\n'
		'    dst:\n'
		'      node: nowhere\n'
		'      port: 1\n'
	)
	with pytest.raises(typer.Exit):
		GraphConfig.from_file(tmp_path / 'graph.yaml')


def test_no_source_capable_node_detected(logging_handler):
	# Both nodes require input "a"; neither is source-capable.
	# a → b: edge validation passes (cycle_mod emits on default).
	# Static validation detects no_source and has_deadlock.
	cycle_map = {**_MODULE_MAP, "cycle_mod": _CycleModule}
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return cycle_map if call_count[0] == 1 else {}

	config = _make_config(
		[_node("a", "cycle_mod"), _node("b", "cycle_mod")],
		[_edge("a", "default", "b", 1)],
	)
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		with pytest.raises(typer.Exit):
			Graph.from_config(config)
