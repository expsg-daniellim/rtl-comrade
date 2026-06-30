"""Unit tests for structure.py — walk_ast and ModuleStructure."""

import ast
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.structure import (
	ModuleStructure,
	ModuleStructureArg,
	StructureInvalidTupleError,
	StructureNonStrPortNameError,
	walk_ast,
)


# --- walk_ast ---


def test_walk_ast_visits_flat_body():
	src = "def f():\n    x = 1\n    y = 2\n"
	tree = ast.parse(src)
	func = tree.body[0]
	nodes = list(walk_ast(func))
	node_types = [type(n).__name__ for n in nodes]
	assert "Assign" in node_types


def test_walk_ast_skips_nested_def():
	src = "def f():\n    def inner():\n        return ('x', 1)\n    return None\n"
	tree = ast.parse(src)
	func = tree.body[0]
	nodes = list(walk_ast(func))
	# inner return should not appear; the nested FunctionDef itself appears but its body does not
	returns = [n for n in nodes if isinstance(n, ast.Return)]
	# Only the outer return None should be yielded
	assert len(returns) == 1
	assert returns[0].value.value is None


def test_walk_ast_skips_lambda_body():
	src = "def f():\n    g = lambda: ('x', 1)\n    return None\n"
	tree = ast.parse(src)
	func = tree.body[0]
	nodes = list(walk_ast(func))
	returns = [n for n in nodes if isinstance(n, ast.Return)]
	assert len(returns) == 1


def test_walk_ast_yields_top_function_node():
	src = "def f():\n    pass\n"
	tree = ast.parse(src)
	func = tree.body[0]
	nodes = list(walk_ast(func))
	assert func in nodes


# --- ModuleStructure argument inference ---


class _NoArgs:
	def run(self):
		return None


class _TwoArgs:
	def run(self, a, b):
		return None


class _TypedWithDefault:
	def run(self, a: int, b: int = 0):
		return None


def test_args_no_params():
	s = ModuleStructure(_NoArgs)
	assert s.args == []  # pylint: disable=use-implicit-booleaness-not-comparison


def test_args_two_plain():
	s = ModuleStructure(_TwoArgs)
	assert len(s.args) == 2
	assert s.args[0] == ModuleStructureArg("a")
	assert s.args[1] == ModuleStructureArg("b")
	assert s.args[0].has_default is False
	assert s.args[1].has_default is False
	assert s.args[0].type_ is None


def test_args_typed_with_default():
	s = ModuleStructure(_TypedWithDefault)
	assert len(s.args) == 2
	assert s.args[0].has_default is False
	assert s.args[0].type_ == str(int)
	assert s.args[1].has_default is True
	assert s.args[1].type_ == str(int)


class _VarPositional:
	def run(self, *args):
		return None


class _VarKeyword:
	def run(self, **kwargs):
		return None


class _MixedVarAndNormal:
	def run(self, a, *args, b, **kwargs):
		return None


def test_args_definite_inputs_true():
	s = ModuleStructure(_TwoArgs)
	assert s.definite_inputs is True


def test_args_var_positional_excluded():
	s = ModuleStructure(_VarPositional)
	assert s.args == []  # pylint: disable=use-implicit-booleaness-not-comparison
	assert s.definite_inputs is False


def test_args_var_keyword_excluded():
	s = ModuleStructure(_VarKeyword)
	assert s.args == []  # pylint: disable=use-implicit-booleaness-not-comparison
	assert s.definite_inputs is False


def test_args_mixed_variadic_excludes_variadic_keeps_normal():
	s = ModuleStructure(_MixedVarAndNormal)
	assert len(s.args) == 2
	assert s.args[0] == ModuleStructureArg("a")
	assert s.args[1] == ModuleStructureArg("b")
	assert s.definite_inputs is False


# --- ModuleStructure emit inference ---


class _ReturnNone:
	def run(self):
		return None


class _ReturnValue:
	def run(self):
		return 42


class _ReturnNamedTuple:
	def run(self):
		return ("out", 42)


class _ReturnDynamic:
	def run(self, port):
		return (port, 42)


class _ReturnMixed:
	def run(self, x):
		if x:
			return 42
		return ("out", x)


class _YieldDefault:
	def run(self):
		yield "x"


class _YieldNamedPort:
	def run(self):
		yield ("port", 1)
		yield ("port", 2)


class _NestedDef:
	def run(self):
		def inner():  # pylint: disable=unused-variable
			return ("x", 1)


def test_emit_return_none():
	s = ModuleStructure(_ReturnNone)
	assert s.emits == []  # pylint: disable=use-implicit-booleaness-not-comparison
	assert s.definite_emits is True


def test_emit_return_value():
	s = ModuleStructure(_ReturnValue)
	assert "default" in s.emits
	assert s.definite_emits is True


def test_emit_return_named_tuple():
	s = ModuleStructure(_ReturnNamedTuple)
	assert s.emits == ["out"]
	assert s.definite_emits is True


def test_emit_return_dynamic():
	s = ModuleStructure(_ReturnDynamic)
	assert s.emits == []  # pylint: disable=use-implicit-booleaness-not-comparison
	assert s.definite_emits is False


def test_emit_mixed():
	s = ModuleStructure(_ReturnMixed)
	assert "default" in s.emits
	assert "out" in s.emits
	assert s.definite_emits is True


def test_emit_yield_default():
	s = ModuleStructure(_YieldDefault)
	assert "default" in s.emits
	assert s.definite_emits is True


def test_emit_yield_named_port():
	s = ModuleStructure(_YieldNamedPort)
	assert s.emits == ["port"]
	assert s.definite_emits is True


def test_emit_nested_def_ignored():
	s = ModuleStructure(_NestedDef)
	assert s.emits == []  # pylint: disable=use-implicit-booleaness-not-comparison
	assert s.definite_emits is True


# --- ModuleStructure finalise emit inference ---


class _FinaliseNamedPort:
	def run(self):
		return None

	def finalise(self):
		return ("flushed", 1)


class _FinaliseDefault:
	def run(self):
		return None

	def finalise(self):
		return 42


class _FinaliseYield:
	def run(self):
		return None

	def finalise(self):
		yield ("summary", 1)


class _FinaliseDynamic:
	def run(self):
		return None

	def finalise(self):
		port = "x"
		return (port, 1)


class _RunAndFinaliseDistinctPorts:
	def run(self):
		return ("from_run", 1)

	def finalise(self):
		return ("from_finalise", 2)


class _RunAndFinaliseBothDefault:
	def run(self):
		return 1

	def finalise(self):
		return 2


class _NonCallableFinalise:
	finalise = 5

	def run(self):
		return None


class _FinaliseInvalidTuple:
	def run(self):
		return None

	def finalise(self):
		return (1, 2, 3)


def test_emit_finalise_named_port():
	s = ModuleStructure(_FinaliseNamedPort)
	assert s.emits == ["flushed"]
	assert s.definite_emits is True


def test_emit_finalise_default():
	s = ModuleStructure(_FinaliseDefault)
	assert "default" in s.emits
	assert s.definite_emits is True


def test_emit_finalise_yield():
	s = ModuleStructure(_FinaliseYield)
	assert s.emits == ["summary"]
	assert s.definite_emits is True


def test_emit_finalise_dynamic():
	s = ModuleStructure(_FinaliseDynamic)
	assert s.emits == []  # pylint: disable=use-implicit-booleaness-not-comparison
	assert s.definite_emits is False


def test_emit_run_and_finalise_distinct_ports():
	s = ModuleStructure(_RunAndFinaliseDistinctPorts)
	assert s.emits == ["from_run", "from_finalise"]
	assert s.definite_emits is True


def test_emit_run_and_finalise_both_default_dedup():
	s = ModuleStructure(_RunAndFinaliseBothDefault)
	assert s.emits == ["default"]
	assert s.definite_emits is True


def test_emit_non_callable_finalise_ignored():
	s = ModuleStructure(_NonCallableFinalise)
	assert s.emits == []  # pylint: disable=use-implicit-booleaness-not-comparison
	assert s.definite_emits is True


def test_finalise_invalid_tuple_raises():
	with pytest.raises(StructureInvalidTupleError) as exc_info:
		ModuleStructure(_FinaliseInvalidTuple)
	assert len(exc_info.value.tuple_) == 3


# --- Error cases ---


class _ThreeElementTuple:
	def run(self):
		return (1, 2, 3)


class _NonStrPortName:
	def run(self):
		return (42, "value")


def test_three_element_tuple_raises():
	with pytest.raises(StructureInvalidTupleError) as exc_info:
		ModuleStructure(_ThreeElementTuple)
	assert exc_info.value.lineno is not None
	assert len(exc_info.value.tuple_) == 3


def test_non_str_port_name_raises():
	with pytest.raises(StructureNonStrPortNameError) as exc_info:
		ModuleStructure(_NonStrPortName)
	assert exc_info.value.port_name == 42


# --- Fatal paths — getsource / ast.parse / signature failures ---


def test_collect_emits_non_callable_method_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		ModuleStructure.collect_emits("M", SimpleNamespace(__name__="run"))


def test_run_signature_type_error_fatal(logging_handler):
	with patch.object(inspect, "signature", side_effect=TypeError("uninspectable")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_run_signature_value_error_fatal(logging_handler):
	with patch.object(inspect, "signature", side_effect=ValueError("wrapped")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_getsource_os_error_fatal(logging_handler):
	with patch.object(inspect, "getsource", side_effect=OSError(13, "Permission denied")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_getsource_type_error_fatal(logging_handler):
	with patch.object(inspect, "getsource", side_effect=TypeError("unloadable")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_getsource_value_error_fatal(logging_handler):
	with patch.object(inspect, "getsource", side_effect=ValueError("wrapped cycle")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_ast_parse_syntax_error_fatal(logging_handler):
	with patch.object(ast, "parse", side_effect=SyntaxError("bad syntax")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_ast_parse_value_error_fatal(logging_handler):
	with patch.object(ast, "parse", side_effect=ValueError("value error")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_ast_parse_type_error_fatal(logging_handler):
	with patch.object(ast, "parse", side_effect=TypeError("type error")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_ast_parse_memory_error_fatal(logging_handler):
	with patch.object(ast, "parse", side_effect=MemoryError("out of memory")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)


def test_ast_parse_recursion_error_fatal(logging_handler):
	with patch.object(ast, "parse", side_effect=RecursionError("max recursion depth")):
		with pytest.raises(typer.Exit):
			ModuleStructure(_NoArgs)
