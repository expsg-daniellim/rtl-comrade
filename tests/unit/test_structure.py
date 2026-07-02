"""Unit tests for structure.py — walk_ast and ModuleStructure."""

import ast
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.api import REST
from rtl_comrade.structure import (
	ModuleStructure,
	ModuleStructureArg,
	StructureInvalidTupleError,
	StructureNonStrPortNameError,
	expand_output_groups,
	partition_over,
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
	assert s.args[0] == ModuleStructureArg("a", "a")
	assert s.args[1] == ModuleStructureArg("b", "b")
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
	assert s.args[0] == ModuleStructureArg("a", "a")
	assert s.args[1] == ModuleStructureArg("b", "b")
	assert s.definite_inputs is False


class _ReservedUnderscore:
	def run(self, list_, class_):
		return None


class _NonReservedUnderscore:
	def run(self, foo_):
		return None


class _PortNameCollision:
	def run(self, list, list_):  # pylint: disable=redefined-builtin
		return None


def test_args_reserved_underscore_stripped():
	s = ModuleStructure(_ReservedUnderscore)
	assert s.args[0].name == "list" and s.args[0].param == "list_"  # builtin
	assert s.args[1].name == "class" and s.args[1].param == "class_"  # keyword


def test_args_non_reserved_underscore_kept():
	s = ModuleStructure(_NonReservedUnderscore)
	assert s.args[0] == ModuleStructureArg("foo_", "foo_")


def test_args_port_name_collision_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		ModuleStructure(_PortNameCollision)


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


def test_parse_emits_non_callable_method_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		ModuleStructure.parse_emits("M", SimpleNamespace(__name__="run"))


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


# --- ModuleStructure arm determination ---


class _IfElse:
	def run(self, x):
		if x:
			yield ("a", 1)
		else:
			yield ("b", 2)


class _ForLoop:
	def run(self, xs):
		for i in xs:
			yield ("a", i)


class _WhileLoop:
	def run(self, n):
		while n:
			yield ("a", n)


class _MatchCase:
	def run(self, x):
		match x:
			case 1:
				yield ("a", 1)
			case _:
				yield ("b", 2)


class _TryExcept:
	def run(self):
		try:
			yield ("a", 1)
		except Exception:  # pylint: disable=broad-except
			yield ("b", 2)


class _WithBlock:
	def run(self, ctx):
		with ctx:
			yield ("a", 1)


class _MixedCond:
	def run(self, x):
		yield ("always", 0)
		if x:
			yield ("cond", 1)


class _MultiPath:
	def run(self, x):
		if x:
			yield ("a", 1)
		else:
			yield ("a", 2)


class _DynBranch:
	"""Dynamic emitter: a named 'stop' arm versus a dynamic passthrough arm."""

	def run(self, **edges):
		if edges:
			yield ("stop", 1)
		else:
			for k, v in edges.items():
				yield (k, v)


def test_arms_if_else_exclusive():
	s = ModuleStructure(_IfElse)
	assert set(s.arms) == {frozenset({"a"}), frozenset({"b"})}


def test_arms_for_loop_conditional():
	s = ModuleStructure(_ForLoop)
	assert set(s.arms) == {frozenset({"a"})}


def test_arms_while_loop_conditional():
	s = ModuleStructure(_WhileLoop)
	assert set(s.arms) == {frozenset({"a"})}


def test_arms_match_cases_exclusive():
	s = ModuleStructure(_MatchCase)
	assert set(s.arms) == {frozenset({"a"}), frozenset({"b"})}


def test_arms_try_except_independent_singletons():
	s = ModuleStructure(_TryExcept)
	assert set(s.arms) == {frozenset({"a"}), frozenset({"b"})}


def test_arms_with_block_unconditional():
	s = ModuleStructure(_WithBlock)
	assert s.emits == ["a"]
	assert s.arms == []  # pylint: disable=use-implicit-booleaness-not-comparison


def test_arms_mixed_conditional_and_unconditional():
	s = ModuleStructure(_MixedCond)
	assert set(s.arms) == {frozenset({"cond"})}  # 'always' is unconditional, so in no arm


def test_arms_multi_path_port_is_unconditional():
	s = ModuleStructure(_MultiPath)
	assert s.emits == ["a"]
	assert s.arms == []  # 'a' emitted under two guards, so it belongs to no single arm  # pylint: disable=use-implicit-booleaness-not-comparison


# --- expand_output_groups ---


def test_expand_output_groups_rest():
	arms = expand_output_groups({"stop": ["stop"], "pass": REST}, {"stop", "a", "b"}, "M")
	assert set(arms) == {frozenset({"stop"}), frozenset({"a", "b"})}


def test_expand_output_groups_rest_empty_omitted():
	arms = expand_output_groups({"g": ["a", "b"], "r": REST}, {"a", "b"}, "M")
	assert arms == [frozenset({"a", "b"})]


def test_expand_output_groups_multiple_rest_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		expand_output_groups({"x": REST, "y": REST}, {"a"}, "M")


def test_expand_output_groups_overlapping_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		expand_output_groups({"g1": ["a"], "g2": ["a"]}, {"a"}, "M")


def test_expand_output_groups_unknown_port_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		expand_output_groups({"g": ["z"]}, {"a"}, "M")


# --- partition_over ---


def test_partition_over_groups_and_always():
	arm = frozenset({"a", "b", "dyn"})
	part, always = partition_over({"a", "b", "c"}, {"a": arm, "b": arm})
	assert part == frozenset({frozenset({"a", "b"})})
	assert always == frozenset({"c"})


# --- ModuleStructure.resolve_arms matrix ---


def test_resolve_arms_definite_no_declaration():
	# _IfElse: 'a' and 'b' are exclusive arms.
	assert ModuleStructure(_IfElse).resolve_arms({"a", "b"}, None) == {"a": frozenset({"a"}), "b": frozenset({"b"})}


def test_resolve_arms_nondefinite_no_declaration_shared_arm():
	# _ReturnDynamic emits nothing statically, so the fallback treats all outputs as one shared arm.
	result = ModuleStructure(_ReturnDynamic).resolve_arms({"a", "b"}, None)
	assert result == {"a": frozenset({"a", "b"}), "b": frozenset({"a", "b"})}


def test_resolve_arms_definite_declaration_agrees():
	assert ModuleStructure(_IfElse).resolve_arms({"a", "b"}, {"g1": ["a"], "g2": ["b"]}) == {"a": frozenset({"a"}), "b": frozenset({"b"})}


def test_resolve_arms_nondefinite_declaration_fills_dynamic():
	result = ModuleStructure(_DynBranch).resolve_arms({"stop", "x", "y"}, {"stop": ["stop"], "pass": REST})
	assert result["stop"] == frozenset({"stop"})
	assert result["x"] == frozenset({"x", "y"})


def test_resolve_arms_declaration_contradicts_ast_fatal(logging_handler):
	# _IfElse's AST proves 'a' and 'b' are separate arms; the declaration lumps them together.
	with pytest.raises(typer.Exit):
		ModuleStructure(_IfElse).resolve_arms({"a", "b"}, {"g": ["a", "b"]})
