"""Unit tests for module.py — GraphModule.from_module and GraphModule.construct_node_ports."""

import inspect
from collections import OrderedDict
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.config import GraphConfigNode, GraphConfigNodePlugin, GraphConfigEdge, GraphConfigSrcPort, GraphConfigDstPort
from rtl_comrade.module import GraphModule, PortInvalidMappingTarget, PortNonDefinitePositionalDestinationError
from rtl_comrade.port import Port


# ---------------------------------------------------------------------------
# Module classes at module scope (inspect.getsource requires top-level definitions)
# ---------------------------------------------------------------------------


class _MinimalModule:
	def run(self):
		return None


class _ModuleWithConfig:
	def __init__(self, config):
		pass

	def run(self):
		return None


class _ModuleWithConfigClass:
	from serde import serde as _serde  # pylint: disable=import-outside-toplevel

	@_serde  # pylint: disable=undefined-variable
	class Config:
		value: int = 0

	def __init__(self, config):
		pass

	def run(self):
		return None


class _ModuleWithId:
	def __init__(self, id):  # pylint: disable=redefined-builtin
		pass

	def run(self):
		return None


class _ModuleWithIdAndConfig:
	def __init__(self, id, config):  # pylint: disable=redefined-builtin
		pass

	def run(self):
		return None


class _OneInputModule:
	def run(self, a):
		return a


class _TwoInputModule:
	def run(self, a, b):
		return a + b


class _DefaultInputModule:
	def run(self, a, b=10):
		return a + b


class _KwargsModule:
	def run(self, **kwargs):
		return None


class _VarArgsModule:
	def run(self, *args):
		return None


class _InvalidTupleModule:
	def run(self):
		return (1, 2, 3)  # three-element tuple → StructureInvalidTupleError


class _NonStrPortNameModule:
	def run(self):
		return (42, "value")  # non-string port name → StructureNonStrPortNameError


# ---------------------------------------------------------------------------
# Happy paths — structure and port detection
# ---------------------------------------------------------------------------


def test_from_module_returns_graphmodule(logging_handler):
	gm = GraphModule.from_module(_MinimalModule)
	assert isinstance(gm, GraphModule)


def test_name_is_class_name(logging_handler):
	gm = GraphModule.from_module(_MinimalModule)
	assert gm.name == "_MinimalModule"


def test_module_attr_is_the_class(logging_handler):
	gm = GraphModule.from_module(_MinimalModule)
	assert gm.Module is _MinimalModule


def test_has_id_false_when_no_id_param(logging_handler):
	gm = GraphModule.from_module(_MinimalModule)
	assert gm.has_id is False


def test_has_id_true_when_id_param_present(logging_handler):
	gm = GraphModule.from_module(_ModuleWithId)
	assert gm.has_id is True


def test_has_config_false_when_no_config_param(logging_handler):
	gm = GraphModule.from_module(_MinimalModule)
	assert gm.has_config is False


def test_has_config_true_when_config_param_present(logging_handler):
	gm = GraphModule.from_module(_ModuleWithConfig)
	assert gm.has_config is True


def test_defines_config_false_when_no_config_class(logging_handler):
	gm = GraphModule.from_module(_ModuleWithConfig)
	assert gm.defines_config is False


def test_defines_config_true_when_config_class_present(logging_handler):
	gm = GraphModule.from_module(_ModuleWithConfigClass)
	assert gm.defines_config is True


def test_both_has_id_and_has_config(logging_handler):
	gm = GraphModule.from_module(_ModuleWithIdAndConfig)
	assert gm.has_id is True
	assert gm.has_config is True


# ---------------------------------------------------------------------------
# Ports — definite inputs
# ---------------------------------------------------------------------------


def test_ports_empty_for_no_inputs(logging_handler):
	gm = GraphModule.from_module(_MinimalModule)
	assert gm.ports == OrderedDict()


def test_ports_one_input(logging_handler):
	gm = GraphModule.from_module(_OneInputModule)
	assert list(gm.ports.keys()) == ["a"]
	assert isinstance(gm.ports["a"], Port)


def test_ports_two_inputs_ordered(logging_handler):
	gm = GraphModule.from_module(_TwoInputModule)
	assert list(gm.ports.keys()) == ["a", "b"]


def test_ports_has_default_propagated(logging_handler):
	gm = GraphModule.from_module(_DefaultInputModule)
	assert gm.ports["a"].has_default is False
	assert gm.ports["b"].has_default is True


# ---------------------------------------------------------------------------
# Ports — non-definite inputs (varargs/kwargs → empty ports)
# ---------------------------------------------------------------------------


def test_ports_empty_for_varargs_module(logging_handler):
	gm = GraphModule.from_module(_VarArgsModule)
	assert gm.ports == OrderedDict()
	assert gm.structure.definite_inputs is False


def test_ports_empty_for_kwargs_module(logging_handler):
	gm = GraphModule.from_module(_KwargsModule)
	assert gm.ports == OrderedDict()
	assert gm.structure.definite_inputs is False


# ---------------------------------------------------------------------------
# Warning — config param without Config class
# ---------------------------------------------------------------------------


def test_config_mismatch_warns_not_errors(logging_handler):
	GraphModule.from_module(_ModuleWithConfig)
	assert logging_handler.failure is False  # warn, not error


# ---------------------------------------------------------------------------
# Fatal paths
# ---------------------------------------------------------------------------


def test_unavailable_signature_fatal(logging_handler):
	with patch.object(inspect, "signature", side_effect=TypeError("uninspectable")):
		with pytest.raises(typer.Exit):
			GraphModule.from_module(_MinimalModule)


def test_unavailable_signature_value_error_fatal(logging_handler):
	with patch.object(inspect, "signature", side_effect=ValueError("wrapped")):
		with pytest.raises(typer.Exit):
			GraphModule.from_module(_MinimalModule)


def test_invalid_tuple_structure_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphModule.from_module(_InvalidTupleModule)


def test_non_str_port_name_structure_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		GraphModule.from_module(_NonStrPortNameModule)


# ---------------------------------------------------------------------------
# Frozen — descriptor is immutable
# ---------------------------------------------------------------------------


def test_graphmodule_is_frozen(logging_handler):
	gm = GraphModule.from_module(_MinimalModule)
	with pytest.raises((AttributeError, TypeError)):
		gm.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# construct_node_ports — contract_port_mappings
# ---------------------------------------------------------------------------


class _MixedDefaultModule:
	def run(self, a, b=0):
		return None


def _node(id_, module_name, mappings=None):
	return GraphConfigNode(id=id_, module=GraphConfigNodePlugin(name=module_name), contract_port_mappings=mappings)


def _edge(src_node, src_port, dst_node, dst_port):
	return GraphConfigEdge(src=GraphConfigSrcPort(node=src_node, port=src_port), dst=GraphConfigDstPort(node=dst_node, port=dst_port))


def test_construct_node_ports_with_mappings(logging_handler):
	gm = GraphModule.from_module(_MixedDefaultModule)
	node = _node("n", "_MixedDefaultModule", {"cp_a": ["a"], "cp_b": ["b"]})
	ports = gm.construct_node_ports(node, [])
	assert list(ports.keys()) == ["cp_a", "cp_b"]
	assert ports["cp_a"].has_default is False
	assert ports["cp_b"].has_default is True


def test_construct_node_ports_invalid_mapping_target(logging_handler):
	gm = GraphModule.from_module(_MixedDefaultModule)
	node = _node("n", "_MixedDefaultModule", {"cp_a": ["nonexistent"]})
	with pytest.raises(PortInvalidMappingTarget) as exc_info:
		gm.construct_node_ports(node, [])
	assert exc_info.value.targets == ["nonexistent"]


def test_construct_node_ports_empty_targets_no_default(logging_handler):
	gm = GraphModule.from_module(_MixedDefaultModule)
	node = _node("n", "_MixedDefaultModule", {"cp_a": []})
	ports = gm.construct_node_ports(node, [])
	assert ports["cp_a"].has_default is False


def test_construct_node_ports_non_definite_string_ports(logging_handler):
	gm = GraphModule.from_module(_KwargsModule)
	node = _node("agg", "_KwargsModule")
	edges = [ _edge("src", "default", "agg", "x"), _edge("src2", "default", "agg", "y") ]
	ports = gm.construct_node_ports(node, edges)
	assert list(ports.keys()) == ["x", "y"]


def test_construct_node_ports_non_definite_positional_rejects(logging_handler):
	gm = GraphModule.from_module(_KwargsModule)
	node = _node("agg", "_KwargsModule")
	edges = [ _edge("src", "default", "agg", 1) ]
	with pytest.raises(PortNonDefinitePositionalDestinationError) as exc_info:
		gm.construct_node_ports(node, edges)
	assert exc_info.value.ports == [1]


def test_construct_node_ports_definite_returns_copy(logging_handler):
	gm = GraphModule.from_module(_OneInputModule)
	node = _node("n", "_OneInputModule")
	ports = gm.construct_node_ports(node, [])
	assert list(ports.keys()) == ["a"]
	assert ports["a"] is not gm.ports["a"]  # deep copy, not same object


def test_construct_node_ports_kwargs_skips_target_check(logging_handler):
	gm = GraphModule.from_module(_KwargsModule)
	node = _node("n", "_KwargsModule", {"cp_a": ["anything"]})
	ports = gm.construct_node_ports(node, [])
	assert list(ports.keys()) == ["cp_a"]
	assert ports["cp_a"].has_default is False
