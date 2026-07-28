"""Unit tests for config.py — GraphFileConfig deserialization and GraphConfigNodePlugin validation."""

from pathlib import Path

from serde import from_dict

from rtl_comrade.config import (
	GraphFileConfig,
	GraphConfigDstPort,
	GraphConfigEdge,
	GraphConfigNode,
	GraphConfigNodePlugin,
	GraphConfigSrcCLI,
	GraphConfigSrcPort,
)


# --- GraphConfigNode ---


def test_node_required_fields_only():
	n = from_dict(GraphConfigNode, {"id": "foo", "module": "bar"})
	assert n.id == "foo"
	assert n.module.name == "bar"
	assert n.module.config == {}
	assert n.contract.name == ""
	assert n.contract.config == {}
	assert n.module.cli == {}
	assert n.contract.cli == {}


def test_node_full():
	n = from_dict(
		GraphConfigNode,
		{
			"id": "n1",
			"module": {"name": "m1", "config": {"k": 1}},
			"contract": {"name": "c1", "config": {"x": 2}},
		},
	)
	assert n.module.config == {"k": 1}
	assert n.contract.name == "c1"
	assert n.contract.config == {"x": 2}


def test_node_contract_port_mappings_absent_is_none():
	n = from_dict(GraphConfigNode, {"id": "foo", "module": "bar"})
	assert n.contract_port_mappings is None


def test_node_contract_port_mappings():
	n = from_dict(
		GraphConfigNode,
		{
			"id": "n1",
			"module": "m1",
			"contract_port_mappings": {"cp_a": ["a"], "cp_both": ["x", "y"]},
		},
	)
	assert n.contract_port_mappings == {"cp_a": ["a"], "cp_both": ["x", "y"]}


def test_node_cli_config():
	n = from_dict(
		GraphConfigNode,
		{
			"id": "n1",
			"module": {"name": "m1", "cli": {"file": {"cli": "input_file", "type": "str", "help": "Input file"}}},
			"contract": {"cli": {"persistent_inputs": {"cli": "persist", "type": "str"}}},
		},
	)
	assert "file" in n.module.cli
	assert isinstance(n.module.cli["file"], GraphConfigSrcCLI)
	assert n.module.cli["file"].cli == "input_file"
	assert n.module.cli["file"].type == "str"
	assert "persistent_inputs" in n.contract.cli
	assert n.contract.cli["persistent_inputs"].cli == "persist"


# --- GraphConfigNodePlugin.validate_cli_config ---


def test_validate_cli_config_no_cli_params():
	plugin = GraphConfigNodePlugin(name="m")
	errors = plugin.validate_cli_config({}, [])
	assert errors == []


def test_validate_cli_config_registers_new_param():
	plugin = GraphConfigNodePlugin(name="m", cli={"field": GraphConfigSrcCLI(cli="value")})
	clis = {}
	params = []
	errors = plugin.validate_cli_config(clis, params)
	assert errors == []
	assert "value" in clis
	assert len(params) == 1


def test_validate_cli_config_blank_cli_name():
	plugin = GraphConfigNodePlugin(name="m", cli={"field": GraphConfigSrcCLI(cli="")})
	errors = plugin.validate_cli_config({}, [])
	assert len(errors) == 1
	assert errors[0].level == 'error'
	assert errors[0].event == 'blank_cli'


def test_validate_cli_config_duplicate_matching_dedup():
	existing = GraphConfigSrcCLI(cli="value")
	plugin = GraphConfigNodePlugin(name="m", cli={"field": GraphConfigSrcCLI(cli="value")})
	clis = {"value": existing}
	params = []
	errors = plugin.validate_cli_config(clis, params)
	assert errors == []
	assert len(params) == 0


def test_validate_cli_config_duplicate_mismatched():
	existing = GraphConfigSrcCLI(cli="value", default=5)
	plugin = GraphConfigNodePlugin(name="m", cli={"field": GraphConfigSrcCLI(cli="value")})
	errors = plugin.validate_cli_config({"value": existing}, [])
	assert len(errors) == 1
	assert errors[0].level == 'error'
	assert errors[0].event == 'cli_def_mismatch'


def test_validate_cli_config_static_override_warns():
	plugin = GraphConfigNodePlugin(name="m", config={"field": 0}, cli={"field": GraphConfigSrcCLI(cli="value")})
	errors = plugin.validate_cli_config({}, [])
	assert len(errors) == 1
	assert errors[0].level == 'warn'
	assert errors[0].event == 'cli_config_override'


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


def test_dst_port_required_default():
	d = from_dict(GraphConfigDstPort, {"node": "b"})
	assert d.required is False


def test_dst_port_required_explicit():
	d = from_dict(GraphConfigDstPort, {"node": "b", "port": "inp", "required": True})
	assert d.required is True


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
