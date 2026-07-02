"""Unit tests for module.py — GraphModule.from_module."""

import inspect
from collections import OrderedDict
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.module import GraphModule
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
