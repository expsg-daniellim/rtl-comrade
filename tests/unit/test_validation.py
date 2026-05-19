"""Unit tests for validation.py — validate_acyclic and validate_no_static_deadlock."""

import pytest

from rtl_comrade.config import (
    GraphConfig,
    GraphConfigEdge,
    GraphConfigNode,
    GraphConfigSrcPort,
    GraphConfigDstPort,
)
from rtl_comrade.validation import (
    StaticDeadlockValidationResults,
    validate_acyclic,
    validate_no_static_deadlock,
)


# --- validate_acyclic helpers ---

def _node(id_):
    return GraphConfigNode(id=id_, module="m")


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
    result = validate_acyclic(cfg)
    assert all(r is None for r in result)


def test_acyclic_simple_cycle():
    cfg = _config(["a", "b"], [("a", "b"), ("b", "a")])
    result = validate_acyclic(cfg)
    assert any(r is not None for r in result)


def test_acyclic_self_loop():
    cfg = _config(["a"], [("a", "a")])
    result = validate_acyclic(cfg)
    assert any(r is not None for r in result)


def test_acyclic_disconnected():
    cfg = _config(["a", "b", "c"], [("a", "b")])
    result = validate_acyclic(cfg)
    assert all(r is None for r in result)


def test_acyclic_edge_unknown_node():
    cfg = _config(["a", "b"], [("a", "b"), ("b", "unknown")])
    result = validate_acyclic(cfg)
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
# These tests need actual Graph objects, so we use inline module classes + Node.

from collections import OrderedDict
from unittest.mock import MagicMock

from rtl_comrade.graph import Graph
from rtl_comrade.node import Node, Connection
from rtl_comrade.port import Port


def _make_graph(node_specs):
    """
    node_specs: list of (id, port_names_with_defaults)
    port_names_with_defaults: list of (port_name, has_default)
    """
    graph = Graph()
    for node_id, ports in node_specs:
        node = MagicMock()
        node.id = node_id
        node.ports = OrderedDict(
            {name: Port(name=name, has_default=hd) for name, hd in ports}
        )
        node.dsts = []
        graph.nodes[node_id] = node
    return graph


def test_deadlock_well_formed():
    # source node (all-default inputs) → required-input node
    graph = _make_graph([
        ("src", [("out", True)]),
        ("sink", [("inp", False)]),
    ])
    # wire src -> sink
    src_node = graph.nodes["src"]
    sink_node = graph.nodes["sink"]
    conn = MagicMock()
    conn.other_node = sink_node
    conn.other_port = "inp"
    src_node.dsts = [conn]
    result = validate_no_static_deadlock(graph)
    assert result.has_error() is False


def test_deadlock_edgeless_required_input():
    # sink has a required input but no incoming edge
    graph = _make_graph([
        ("src", []),
        ("sink", [("inp", False)]),
    ])
    graph.nodes["src"].dsts = []
    result = validate_no_static_deadlock(graph)
    assert "sink" in result.edgeless_inputs


def test_deadlock_no_source_capable():
    # all nodes require an input
    graph = _make_graph([
        ("a", [("x", False)]),
        ("b", [("y", False)]),
    ])
    result = validate_no_static_deadlock(graph)
    assert result.has_source_capable is False


def test_deadlock_non_reachable():
    # src can run on its own; isolated has no incoming edge from any source
    graph = _make_graph([
        ("src", []),          # source-capable
        ("isolated", [("x", False)]),  # no edge from src
    ])
    result = validate_no_static_deadlock(graph)
    assert "isolated" in result.non_reachable_nodes
