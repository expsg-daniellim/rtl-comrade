"""Unit tests for config.py — GraphFileConfig deserialization."""

from pathlib import Path

from serde import from_dict

from rtl_comrade.config import (
	GraphFileConfig,
	GraphConfigDstPort,
	GraphConfigEdge,
	GraphConfigNode,
	GraphConfigSrcPort,
)


# --- GraphConfigNode ---


def test_node_required_fields_only():
	n = from_dict(GraphConfigNode, {"id": "foo", "module": "bar"})
	assert n.id == "foo"
	assert n.module == "bar"
	assert n.config == {}
	assert n.contract == ""
	assert n.contract_config == {}


def test_node_full():
	n = from_dict(
		GraphConfigNode,
		{
			"id": "n1",
			"module": "m1",
			"config": {"k": 1},
			"contract": "c1",
			"contract_config": {"x": 2},
		},
	)
	assert n.config == {"k": 1}
	assert n.contract == "c1"
	assert n.contract_config == {"x": 2}


# --- GraphConfigSrcPort ---


def test_src_port_default_port():
	s = from_dict(GraphConfigSrcPort, {"node": "a"})
	assert s.node == "a"
	assert s.port == "default"


def test_src_port_explicit():
	s = from_dict(GraphConfigSrcPort, {"node": "a", "port": "out"})
	assert s.port == "out"


# --- GraphConfigDstPort ---


def test_dst_port_default_port():
	d = from_dict(GraphConfigDstPort, {"node": "b"})
	assert d.node == "b"
	assert d.port == 1


def test_dst_port_int():
	d = from_dict(GraphConfigDstPort, {"node": "b", "port": 2})
	assert d.port == 2


def test_dst_port_str():
	d = from_dict(GraphConfigDstPort, {"node": "b", "port": "inp"})
	assert d.port == "inp"


# --- GraphFileConfig ---


def test_graph_config_full():
	data = {
		"nodes": [
			{"id": "n1", "module": "m1"},
			{"id": "n2", "module": "m2"},
		],
		"edges": [
			{"src": {"node": "n1"}, "dst": {"node": "n2"}},
		],
		"modules": ["path/to/mods"],
		"contracts": ["path/to/contracts"],
	}
	cfg = from_dict(GraphFileConfig, data)
	assert len(cfg.nodes) == 2
	assert len(cfg.edges) == 1
	assert cfg.modules == [Path("path/to/mods")]
	assert cfg.contracts == [Path("path/to/contracts")]


def test_graph_config_defaults_lists():
	data = {
		"nodes": [],
		"edges": [],
	}
	cfg = from_dict(GraphFileConfig, data)
	assert cfg.modules == []
	assert cfg.contracts == []


# --- GraphConfigEdge.__structlog__ ---


def test_edge_structlog():
	edge = GraphConfigEdge(
		src=GraphConfigSrcPort(node="a", port="default"),
		dst=GraphConfigDstPort(node="b", port=1),
	)
	result = edge.__structlog__()
	assert isinstance(result, dict)
	assert "src" in result
	assert "dst" in result
