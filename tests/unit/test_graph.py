"""Unit tests for graph.py — Graph.from_config validation."""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from serde import serde, SerdeError
from serde.compat import UserError

from rtl_comrade.config import GraphConfigDstPort, GraphConfigEdge, GraphConfigNode, GraphConfigNodePlugin, GraphConfigSrcCLI, GraphConfigSrcPort, GraphFileConfig
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


class OutputOnlyContract:
	def __init__(self, id, ports):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports

	def process_outputs(self, port:str, value):
		return value


class NoPortParamContract:
	def process_outputs(self, value):
		return value


class NonStrPortParamContract:
	def process_outputs(self, port:int, value):
		return value


class ConfigurableContract:
	"""Serves either end, and carries a config the CLI can write into."""

	@serde
	class Config:
		limit:int = 0

	def __init__(self, id, ports, config):  # pylint: disable=redefined-builtin
		self.id = id
		self.ports = ports
		self.config = config

	async def get_inputs(self):
		from rtl_comrade.api import EndSentinel  # pylint: disable=import-outside-toplevel

		return EndSentinel(self.id)

	def process_outputs(self, port:str, value):
		return value


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


class _MixedDefaultModule:
	"""One default-less input (a) and one default-bearing input (b)."""

	def run(self, a, b=0):
		return None


class _ModuleWithTypedConfig:
	@serde
	class Config:
		value: int = 0

	def __init__(self, config):
		self.cfg = config

	def run(self):
		return None


class _InitCrashMod:
	def __init__(self):
		raise RuntimeError("deliberate init crash")

	def run(self):
		return None


# Mapping helpers
_MODULE_MAP = {
	"source_mod": _SourceModule,
	"sink_mod": _SinkModule,
	"two_input_mod": _TwoInputModule,
	"named_emit_mod": _NamedEmitModule,
	"dynamic_emit_mod": _DynamicEmitModule,
	"kwargs_mod": _KwargsModule,
	"mixed_mod": _MixedDefaultModule,
}
_CONTRACT_MAP = {
	"basic_contract": _BasicContract,
	"output_contract": OutputOnlyContract,
	"no_port_contract": NoPortParamContract,
	"non_str_port_contract": NonStrPortParamContract,
	"configurable_contract": ConfigurableContract,
}


def _node(id_, module, contract=""):
	return GraphConfigNode(id=id_, module=GraphConfigNodePlugin(name=module), contract=GraphConfigNodePlugin(name=contract))


def _mapping_node(id_, module, mappings, contract=""):
	return GraphConfigNode(id=id_, module=GraphConfigNodePlugin(name=module), contract=GraphConfigNodePlugin(name=contract), contract_port_mappings=mappings)


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


def _from_config_with_contracts(config, cli_kwargs=None):
	"""Load with both module and contract mappings."""
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		if call_count[0] == 1:
			return _MODULE_MAP
		return _CONTRACT_MAP

	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		return Graph.from_config(config, cli_kwargs)


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
			nodes=[GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="source_mod")), GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="sink_mod"))],
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
			nodes=[GraphConfigNode(id="src", module=GraphConfigNodePlugin(name="source_mod"))],
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
		nodes=[GraphConfigNode(id="sink", module=GraphConfigNodePlugin(name="default_sink"))],
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


def test_overloaded_srcs_fatal(logging_handler):
	config = _make_config(
		[_node("src1", "source_mod"), _node("src2", "source_mod"), _node("sink", "sink_mod")],
		[_edge("src1", "default", "sink", 1), _edge("src2", "default", "sink", 1)],
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
	assert len(src_node.dsts["default"]) == 1
	assert src_node.dsts["default"][0] is graph.nodes["sink"].ports["a"]


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
	assert "default" in src_node.dsts
	assert src_node.dsts["default"][0] is graph.nodes["sink"].ports["b"]


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
	assert graph.nodes["src"].dsts["default"][0] is graph.nodes["agg"].ports["any_port"]


def test_non_definite_inputs_rejects_positional_dst_port(logging_handler):
	module_map = {**_MODULE_MAP, "kwargs_mod": _KwargsModule}
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return module_map if call_count[0] == 1 else {}

	# A positional (int) port has no canonical order to resolve against on a non-definite surface — fatal.
	config = _make_config(
		[_node("src", "source_mod"), _node("agg", "kwargs_mod")],
		[_edge("src", "default", "agg", 1)],
	)
	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		with pytest.raises(typer.Exit):
			Graph.from_config(config)


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


# --- Contract resolution ---


def test_all_three_contract_fields_warns_obsolete(logging_handler):
	# Both ends overridden leaves the general contract unreachable — a warning, not an error.
	config = _make_config([GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="source_mod"), contract=GraphConfigNodePlugin(name="basic_contract"), input_contract=GraphConfigNodePlugin(name="basic_contract"), output_contract=GraphConfigNodePlugin(name="output_contract"))], [])
	graph = _from_config_with_contracts(config)
	assert isinstance(graph.nodes["n1"].input_contract, _BasicContract)
	assert isinstance(graph.nodes["n1"].output_contract, OutputOnlyContract)
	assert logging_handler.failure is False


def test_output_contract_missing_port_parameter_fatal(logging_handler):
	config = _make_config([GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="source_mod"), output_contract=GraphConfigNodePlugin(name="no_port_contract"))], [])
	with pytest.raises(typer.Exit):
		_from_config_with_contracts(config)


def test_output_contract_non_str_port_annotation_fatal(logging_handler):
	config = _make_config([GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="source_mod"), output_contract=GraphConfigNodePlugin(name="non_str_port_contract"))], [])
	with pytest.raises(typer.Exit):
		_from_config_with_contracts(config)


def test_cli_input_contract_config_override(logging_handler):
	config = _make_config([GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="source_mod"), input_contract=GraphConfigNodePlugin(name="configurable_contract", config={"limit": 0}, cli={"limit": GraphConfigSrcCLI(cli="n", type="int")}))], [])
	graph = _from_config_with_contracts(config, cli_kwargs={"n": 3})
	assert graph.nodes["n1"].input_contract.config.limit == 3


def test_cli_output_contract_config_override(logging_handler):
	config = _make_config([GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="source_mod"), output_contract=GraphConfigNodePlugin(name="configurable_contract", config={"limit": 0}, cli={"limit": GraphConfigSrcCLI(cli="n", type="int")}))], [])
	graph = _from_config_with_contracts(config, cli_kwargs={"n": 5})
	assert graph.nodes["n1"].output_contract.config.limit == 5


# --- Graph-level structural validation (using _CycleModule for valid edges) ---


def test_cyclic_graph_detected_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(GraphFileConfig(
			nodes=[GraphConfigNode(id="a", module=GraphConfigNodePlugin(name="m")), GraphConfigNode(id="b", module=GraphConfigNodePlugin(name="m"))],
			edges=[
				GraphConfigEdge(src=GraphConfigSrcPort(node="a"), dst=GraphConfigDstPort(node="b")),
				GraphConfigEdge(src=GraphConfigSrcPort(node="b"), dst=GraphConfigDstPort(node="a")),
			],
		))


# --- CLI edge errors ---


def test_cli_name_conflicts_with_node_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphConfig.from_file_config(GraphFileConfig(
			nodes=[GraphConfigNode(id="cli-foo", module=GraphConfigNodePlugin(name="m"))],
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


# --- contract_port_mappings ---


def test_contract_port_mappings_definite_surface_resolves(logging_handler):
	# Edges resolve to declared contract ports; Node.ports keys are exactly the contract ports.
	config = _make_config(
		[_node("src", "source_mod"), _mapping_node("dst", "mixed_mod", {"cp_a": ["a"], "cp_b": ["b"]})],
		[_edge("src", "default", "dst", "cp_a")],
	)
	graph = _from_config(config)
	assert set(graph.nodes["dst"].ports.keys()) == {"cp_a", "cp_b"}
	assert graph.nodes["src"].dsts["default"][0] is graph.nodes["dst"].ports["cp_a"]
	# has_default is derived from the targets: a has no default, b does.
	assert graph.nodes["dst"].ports["cp_a"].has_default is False
	assert graph.nodes["dst"].ports["cp_b"].has_default is True
	assert logging_handler.failure is False


def test_contract_port_mappings_default_target_source_capable(logging_handler):
	# A lone node whose only contract port forwards to a defaulted target is source-capable → valid standalone.
	config = _make_config([_mapping_node("n", "mixed_mod", {"cp_b": ["b"]})], [])
	graph = _from_config(config)
	assert graph.nodes["n"].ports["cp_b"].has_default is True
	assert logging_handler.failure is False


def test_contract_port_mappings_defaultless_target_edgeless_fatal(logging_handler):
	# cp_a forwards to default-less a → first-run-required; with no incoming edge it is edgeless → deadlock fatal.
	config = _make_config([_mapping_node("n", "mixed_mod", {"cp_a": ["a"]})], [])
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_contract_port_mappings_bad_target_fatal(logging_handler):
	# Definite module: a target absent from the run(...) signature is fatal (invalid_mapping_target).
	config = _make_config(
		[_node("src", "source_mod"), _mapping_node("dst", "mixed_mod", {"cp_a": ["nonexistent"]})],
		[_edge("src", "default", "dst", "cp_a")],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_contract_port_mappings_empty_targets_no_default(logging_handler):
	# A contract port mapping to no targets forwards to nothing, so it cannot default; fed by an edge the graph is valid.
	config = _make_config(
		[_node("src", "source_mod"), _mapping_node("dst", "mixed_mod", {"cp_a": []})],
		[_edge("src", "default", "dst", "cp_a")],
	)
	graph = _from_config(config)
	assert graph.nodes["dst"].ports["cp_a"].has_default is False
	assert logging_handler.failure is False


def test_contract_port_mappings_empty_targets_edgeless_fatal(logging_handler):
	# An empty target list is first-run-required, so with no incoming edge it is edgeless → deadlock fatal.
	config = _make_config([_mapping_node("n", "mixed_mod", {"cp_a": []})], [])
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_contract_port_mappings_undeclared_dst_port_definite_fatal(logging_handler):
	# An edge to an undeclared contract port is fatal even over a definite module.
	config = _make_config(
		[_node("src", "source_mod"), _mapping_node("dst", "mixed_mod", {"cp_a": ["a"]})],
		[_edge("src", "default", "dst", "cp_unknown")],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_contract_port_mappings_undeclared_dst_port_kwargs_fatal(logging_handler):
	# Node-level definiteness forces strict edge validation even over a **kwargs module.
	config = _make_config(
		[_node("src", "source_mod"), _mapping_node("dst", "kwargs_mod", {"cp_a": ["x"]})],
		[_edge("src", "default", "dst", "cp_unknown")],
	)
	with pytest.raises(typer.Exit):
		_from_config(config)


def test_contract_port_mappings_kwargs_valid_no_warning(logging_handler, caplog):
	# Over a **kwargs module: target check skipped, contract ports are the strict surface, node is definite (no warning).
	config = _make_config(
		[_node("src", "source_mod"), _mapping_node("dst", "kwargs_mod", {"cp_a": ["x"]})],
		[_edge("src", "default", "dst", "cp_a")],
	)
	graph = _from_config(config)
	assert set(graph.nodes["dst"].ports.keys()) == {"cp_a"}
	assert graph.nodes["dst"].definite_inputs is True
	# No signature defaults over a **kwargs module → contract port is first-run-required.
	assert graph.nodes["dst"].ports["cp_a"].has_default is False
	assert logging_handler.failure is False
	assert "non_definite_inputs" not in caplog.text


# --- Module config/init fatal paths (via from_config_node → graph catch) ---


def _from_config_with_module_map(config, module_map):
	call_count = [0]

	def side_effect(paths, namespace):
		call_count[0] += 1
		return module_map if call_count[0] == 1 else {}

	with patch("rtl_comrade.graph.load_plugins", side_effect=side_effect):
		return Graph.from_config(config)


def test_module_config_serde_error_fatal(logging_handler):
	module_map = {**_MODULE_MAP, "typed_config_mod": _ModuleWithTypedConfig}
	config = _make_config([GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="typed_config_mod", config={"value": 0}))], [])
	with patch("rtl_comrade.node.from_dict", side_effect=SerdeError("bad config")):
		with pytest.raises(typer.Exit):
			_from_config_with_module_map(config, module_map)


def test_module_config_user_error_fatal(logging_handler):
	module_map = {**_MODULE_MAP, "typed_config_mod": _ModuleWithTypedConfig}
	config = _make_config([GraphConfigNode(id="n1", module=GraphConfigNodePlugin(name="typed_config_mod", config={"value": 0}))], [])
	with patch("rtl_comrade.node.from_dict", side_effect=UserError("user error")):  # ty: ignore[invalid-argument-type]
		with pytest.raises(typer.Exit):
			_from_config_with_module_map(config, module_map)


def test_module_init_exception_fatal(logging_handler):
	module_map = {**_MODULE_MAP, "crash_mod": _InitCrashMod}
	config = _make_config([_node("n1", "crash_mod")], [])
	with pytest.raises(typer.Exit):
		_from_config_with_module_map(config, module_map)
