"""Unit tests for validation.py — validate_acyclic, validate_no_static_deadlock, and validate_branching."""

from collections import OrderedDict
from unittest.mock import MagicMock

from rtl_comrade.config import GraphConfigEdge, GraphConfigNode, GraphConfigNodePlugin, GraphConfigSrcPort, GraphConfigDstPort
from rtl_comrade.config_graph import GraphConfig
from rtl_comrade.node import Connection
from rtl_comrade.port import Port
from rtl_comrade.structure import ModuleStructure
from rtl_comrade.validation import (
	StaticDeadlockValidationResults,
	validate_acyclic,
	validate_branching,
	validate_no_static_deadlock,
)


# --- validate_acyclic helpers ---


def _node(id_):
	return GraphConfigNode(id=id_, module=GraphConfigNodePlugin(name="m"))


def _edge(src, dst):
	return GraphConfigEdge(
		src=GraphConfigSrcPort(node=src),
		dst=GraphConfigDstPort(node=dst),
	)


def _config(node_ids, edge_pairs):
	return GraphConfig(
		nodes=[_node(n) for n in node_ids],
		edges=[_edge(a, b) for a, b in edge_pairs],
	)


# --- validate_acyclic ---


def test_acyclic_linear():
	cfg = _config(["a", "b", "c"], [("a", "b"), ("b", "c")])
	result = validate_acyclic(cfg.nodes, cfg.edges)
	assert all(r is None for r in result)


def test_acyclic_simple_cycle():
	cfg = _config(["a", "b"], [("a", "b"), ("b", "a")])
	result = validate_acyclic(cfg.nodes, cfg.edges)
	assert any(r is not None for r in result)


def test_acyclic_self_loop():
	cfg = _config(["a"], [("a", "a")])
	result = validate_acyclic(cfg.nodes, cfg.edges)
	assert any(r is not None for r in result)


def test_acyclic_disconnected():
	cfg = _config(["a", "b", "c"], [("a", "b")])
	result = validate_acyclic(cfg.nodes, cfg.edges)
	assert all(r is None for r in result)


def test_acyclic_edge_unknown_node():
	cfg = _config(["a", "b"], [("a", "b"), ("b", "unknown")])
	result = validate_acyclic(cfg.nodes, cfg.edges)
	assert all(r is None for r in result)


# --- StaticDeadlockValidationResults.has_error ---


def test_has_error_false_when_clean():
	r = StaticDeadlockValidationResults(
		edgeless_inputs=[],
		has_source_capable=True,
		non_reachable_nodes=[],
	)
	assert r.has_error() is False


def test_has_error_true_edgeless():
	r = StaticDeadlockValidationResults(edgeless_inputs=["n1"], has_source_capable=True)
	assert r.has_error() is True


def test_has_error_true_no_source():
	r = StaticDeadlockValidationResults(has_source_capable=False)
	assert r.has_error() is True


def test_has_error_true_non_reachable():
	r = StaticDeadlockValidationResults(has_source_capable=True, non_reachable_nodes=["n2"])
	assert r.has_error() is True


# --- validate_no_static_deadlock ---
# Screening runs over PreNodes (port metadata) plus id-space connections keyed by source node id, so the tests build those directly.


def _make_prenodes(node_specs):
	"""
	node_specs: list of (id, port_names_with_defaults)
	port_names_with_defaults: list of (port_name, has_default)
	"""
	prenodes = {}
	for node_id, ports in node_specs:
		pre = MagicMock()
		pre.id = node_id
		pre.ports = OrderedDict({name: Port(name=name, has_default=hd) for name, hd in ports})
		pre.required_ports = set()
		prenodes[node_id] = pre
	return prenodes


def test_deadlock_well_formed():
	# source node (all-default inputs) → required-input node
	prenodes = _make_prenodes(
		[
			("src", [("out", True)]),
			("sink", [("inp", False)]),
		]
	)
	node_dsts = {"src": [Connection("out", "sink", "inp")]}
	result = validate_no_static_deadlock(prenodes, node_dsts)
	assert result.has_error() is False


def test_deadlock_edgeless_required_input():
	# sink has a required input but no incoming edge
	prenodes = _make_prenodes(
		[
			("src", []),
			("sink", [("inp", False)]),
		]
	)
	result = validate_no_static_deadlock(prenodes, {})
	assert "sink" in result.edgeless_inputs


def test_deadlock_no_source_capable():
	# all nodes require an input
	prenodes = _make_prenodes(
		[
			("a", [("x", False)]),
			("b", [("y", False)]),
		]
	)
	result = validate_no_static_deadlock(prenodes, {})
	assert result.has_source_capable is False


def test_deadlock_non_reachable():
	# src can run on its own; isolated has no incoming edge from any source
	prenodes = _make_prenodes(
		[
			("src", []),  # source-capable
			("isolated", [("x", False)]),  # no edge from src
		]
	)
	result = validate_no_static_deadlock(prenodes, {})
	assert "isolated" in result.non_reachable_nodes


def test_deadlock_required_default_port_not_source_capable():
	# A node whose only input has a default but is marked required is not source-capable,
	# so a graph resting on it as the sole source is a deadlock.
	prenodes = _make_prenodes(
		[
			("only", [("inp", True)]),
		]
	)
	prenodes["only"].required_ports = {"inp"}
	result = validate_no_static_deadlock(prenodes, {})
	assert result.has_source_capable is False


# --- validate_branching ---
# Tests build mock PreNodes carrying real ModuleStructure objects (for resolve_arms / exclusive_arms) and call validate_branching directly.


class _SourceModule:
	def run(self):
		return 1


class _SinkModule:
	def run(self, a):
		return None


class _TwoInputModule:
	def run(self, a, b):
		return None


class _BranchModule:
	def run(self):
		if True:  # pylint: disable=using-constant-test
			yield ("p", 1)
		else:
			yield ("q", 2)


class _TwoGuardModule:
	def run(self):
		if True:  # pylint: disable=using-constant-test
			yield ("p", 1)
		if True:  # pylint: disable=using-constant-test
			yield ("q", 2)


class _PassModule:
	def run(self, a):
		return a


class _InputBranchModule:
	def run(self, a):
		if a:
			yield ("p", 1)
		else:
			yield ("q", 2)


class _DefaultInputModule:
	def run(self, a=None):
		return a


def _make_branching_prenode(nid, Module, ports=None, required_ports=None):
	structure = ModuleStructure(Module)
	pre = MagicMock()
	pre.id = nid
	pre.structure = structure
	pre.module = Module
	pre.required_ports = required_ports or set()
	if ports is not None:
		pre.ports = ports
	else:
		pre.ports = OrderedDict({ arg.name: Port(name=arg.name, has_default=arg.has_default) for arg in structure.args })
	return pre


def test_branching_labels_propagate_distinct_arms():
	prenodes = { n.id: n for n in [ _make_branching_prenode("b", _BranchModule), _make_branching_prenode("n", _TwoInputModule) ] }
	node_dsts = { "b": [ Connection("p", "n", "a"), Connection("q", "n", "b") ], "n": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert input_labels["n"]["a"] == frozenset({("b", frozenset({"p"}))})
	assert input_labels["n"]["b"] == frozenset({("b", frozenset({"q"}))})
	assert len(overloaded) == 0


def test_branching_exclusive_arms_may_share_one_input_port():
	prenodes = { n.id: n for n in [ _make_branching_prenode("b", _BranchModule), _make_branching_prenode("sink", _SinkModule) ] }
	node_dsts = { "b": [ Connection("p", "sink", "a"), Connection("q", "sink", "a") ], "sink": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert len(overloaded) == 0
	assert input_labels["sink"]["a"] == frozenset()


def test_branching_exclusive_arms_through_intermediates():
	prenodes = { n.id: n for n in [ _make_branching_prenode("b", _BranchModule), _make_branching_prenode("x", _PassModule), _make_branching_prenode("y", _PassModule), _make_branching_prenode("sink", _SinkModule) ] }
	node_dsts = { "b": [ Connection("p", "x", "a"), Connection("q", "y", "a") ], "x": [ Connection("default", "sink", "a") ], "y": [ Connection("default", "sink", "a") ], "sink": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert len(overloaded) == 0
	assert input_labels["sink"]["a"] == frozenset()


def test_branching_merged_port_keeps_shared_labels():
	prenodes = { n.id: n for n in [ _make_branching_prenode("b", _BranchModule), _make_branching_prenode("c", _InputBranchModule), _make_branching_prenode("sink", _SinkModule) ] }
	node_dsts = { "b": [ Connection("p", "c", "a") ], "c": [ Connection("p", "sink", "a"), Connection("q", "sink", "a") ], "sink": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert len(overloaded) == 0
	assert input_labels["sink"]["a"] == frozenset({("b", frozenset({"p"}))})


def test_branching_labels_empty_for_unbranched_edge():
	prenodes = { n.id: n for n in [ _make_branching_prenode("s", _SourceModule), _make_branching_prenode("k", _SinkModule) ] }
	node_dsts = { "s": [ Connection("default", "k", "a") ], "k": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert input_labels["k"]["a"] == frozenset()
	assert len(overloaded) == 0


def test_branching_overloaded_unconditional_sources():
	prenodes = { n.id: n for n in [ _make_branching_prenode("src1", _SourceModule), _make_branching_prenode("src2", _SourceModule), _make_branching_prenode("sink", _SinkModule) ] }
	node_dsts = { "src1": [ Connection("default", "sink", "a") ], "src2": [ Connection("default", "sink", "a") ], "sink": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert ("sink", "a") in overloaded


def test_branching_overloaded_independent_guards():
	prenodes = { n.id: n for n in [ _make_branching_prenode("g", _TwoGuardModule), _make_branching_prenode("sink", _SinkModule) ] }
	node_dsts = { "g": [ Connection("p", "sink", "a"), Connection("q", "sink", "a") ], "sink": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert ("sink", "a") in overloaded


def test_branching_non_gating_input_does_not_propagate():
	prenodes = { n.id: n for n in [ _make_branching_prenode("b", _BranchModule), _make_branching_prenode("relay", _DefaultInputModule), _make_branching_prenode("sink", _SinkModule) ] }
	node_dsts = { "b": [ Connection("p", "relay", "a") ], "relay": [ Connection("default", "sink", "a") ], "sink": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert input_labels["relay"]["a"] == frozenset({("b", frozenset({"p"}))})
	assert input_labels["sink"]["a"] == frozenset()
	assert len(overloaded) == 0


def test_branching_required_default_port_propagates():
	prenodes = { n.id: n for n in [ _make_branching_prenode("b", _BranchModule), _make_branching_prenode("relay", _DefaultInputModule, required_ports={"a"}), _make_branching_prenode("sink", _SinkModule) ] }
	node_dsts = { "b": [ Connection("p", "relay", "a") ], "relay": [ Connection("default", "sink", "a") ], "sink": [] }
	input_labels, overloaded = validate_branching(prenodes, node_dsts)
	assert input_labels["sink"]["a"] == frozenset({("b", frozenset({"p"}))})
	assert len(overloaded) == 0
