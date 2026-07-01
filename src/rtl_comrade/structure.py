"""Static analysis of module signatures and emitted output-port names."""

import ast
from collections import deque, defaultdict
from dataclasses import dataclass
import inspect
from inspect import Parameter
import textwrap
import typing
from typing import cast, NamedTuple

import structlog

from .api import RestSentinel
from .logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

# BFS of the AST filtering out nested function nodes.
def walk_ast(node):
	"""Breadth-first AST walk that skips nested function bodies.

	Args:
		node: Root AST node to traverse.

	Yields:
		AST nodes reachable from the root while excluding nested function scopes.
	"""

	queue = deque([node])
	passed_top = False # Keep tracking of passing the top-level function node
	while queue:
		n = queue.popleft()
		if not isinstance(n, (ast.FunctionDef, ast.Lambda, ast.AsyncFunctionDef)):
			queue.extend(ast.iter_child_nodes(n))
		elif not passed_top:
			passed_top = True
			queue.extend(ast.iter_child_nodes(n))

		yield n

@dataclass(frozen=True, slots=True)
class StructureInvalidTupleError(Exception):
	"""Raised when a returned or yielded tuple has an invalid shape.

	Attributes:
		name: The module class name being analyzed.
		lineno: The line number where the invalid tuples are found.
		tuple_: The invalid tuple elements found in the AST.
	"""

	name: str
	lineno: int
	tuple_: tuple

@dataclass(frozen=True, slots=True)
class StructureNonStrPortNameError(Exception):
	"""Raised when a static emitted port name is not a string.

	Attributes:
		name: The module class name being analyzed.
		lineno: The line number where the invalid port name was found.
		port_name: The invalid non-string port-name value encountered in the AST.
	"""

	name: str
	lineno: int
	port_name: typing.Any

@dataclass(frozen=True, slots=True)
class ModuleStructureArg:
	"""One inferred module input argument from a module ``run(...)`` signature.

	Attributes:
		name: Input-port name inferred from the parameter name.
		type_: Stringified annotation, if present on the parameter.
		has_default: Whether the parameter has a Python default value.
	"""

	name: str
	type_: str | None = None
	has_default: bool = False

class EmitInfo(NamedTuple):
	"""Output surface parsed from one method's AST.

	Attributes:
		emits: Named output ports in emit order.
		definite: Whether the output-port set is believed to be complete.
		default: Whether a ``"default"``-port emit was found.
		arms: Branch-arm partition over the named ports.
	"""

	emits: list[str]
	definite: bool
	default: bool
	arms: list[frozenset[str]]

@dataclass(slots=True)
class ModuleStructure:
	"""Statically inferred view of one module's input and output surface.

	Attributes:
		name: Module class name, used for error reporting.
		args: Ordered input arguments inferred from ``run(...)``.
		emits: Statically known output-port names.
		definite_emits: Whether ``emits`` is believed to be complete.
		definite_inputs: Whether ``args`` is believed to be complete.
		arms: Branch-arm partition over statically-named output ports — each arm is the set of
			ports sharing one guarding branch-path; unconditional ports appear in no arm.
	"""

	name: str
	args: list[ModuleStructureArg]
	emits: list[str]
	definite_emits: bool
	definite_inputs: bool
	arms: list[frozenset[str]]

	def __init__(self, Module):
		"""Analyze one module class and infer its runtime structure.

		Args:
			Module: Module plugin class whose ``run(...)`` signature and ``run(...)``/``finalise()`` emits should be inspected.

		Returns:
			None.
		"""

		# Assume that Module has been pre-validated to have run.
		self.name = Module.__name__

		# Populate args from the function signature
		try:
			sig = inspect.signature(Module.run)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', exc_info=e)

		non_self = [(name, param) for (name, param) in sig.parameters.items() if name != 'self']
		self.definite_inputs = not any(param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD) for (_, param) in non_self)
		self.args = [ ModuleStructureArg(
			name=name,
			type_=str(param.annotation) if param.annotation != Parameter.empty else None,
			has_default=param.default != Parameter.empty,
		) for (name, param) in non_self if param.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD) ]

		# Emits come from run and, when it resolves to a callable (as node.py guards at runtime), finalise.
		run_info = self.parse_emits(Module.__name__, Module.run)
		self.emits = run_info.emits
		self.definite_emits = run_info.definite
		self.arms = run_info.arms
		default = run_info.default

		if hasattr(Module, 'finalise') and callable(Module.finalise):
			finalise_info = self.parse_emits(Module.__name__, Module.finalise)
			self.emits.extend(port for port in finalise_info.emits if port not in self.emits)
			self.definite_emits = self.definite_emits and finalise_info.definite
			default = default or finalise_info.default

		if default:
			self.emits.insert(0, 'default')

	@staticmethod
	def parse_emits(name, method) -> EmitInfo:
		"""Walk one method's AST for its emit ports and the guarding branch-path of each.

		Args:
			name: Module class name, used only for error reporting.
			method: The ``run`` or ``finalise`` function whose source is analysed.

		Returns:
			An ``EmitInfo``. Each arm groups the ports emitted under one guarding branch-path; ports
			emitted unconditionally or under several guards are in no arm.
		"""

		# Make sure method is callable first
		if not callable(method):
			log.fatal(f'uncallable_{method.__name__}')

		# Parse AST in steps to catch individual Exceptions from each step
		try:
			src = textwrap.dedent(inspect.getsource(method))
		except OSError as e:
			log.fatal('file_unavailable', err=e.strerror, errno=e.errno, exc_info=e)
		except TypeError as e:
			log.fatal('unloadable', message=str(e), exc_info=e)
		except ValueError as e:
			log.fatal('wrapped_cycle', exc_info=e)

		try:
			ast_tree = ast.parse(src)
		except SyntaxError as e:
			log.fatal('syntax_error', filename=e.filename, lineno=e.lineno, offset=e.offset, text=e.text, end_lineno=e.end_lineno, end_offset=e.end_offset, exc_info=e)
		except ValueError as e:
			log.fatal('value_error', message=str(e), exc_info=e)
		except TypeError as e:
			log.fatal('type_error', message=str(e), exc_info=e)
		except MemoryError as e:
			log.fatal('memory_error', message=str(e), exc_info=e)
		except RecursionError as e:
			log.fatal('recursion_err', message=str(e), exc_info=e)

		emits:list[str] = []
		definite = True
		default = False
		port_paths:dict[str, set[tuple]] = {} # port name -> distinct guarding branch-paths it is emitted under

		def record(node, path):
			nonlocal definite, default
			if isinstance(node, ast.YieldFrom): # sub-generator yields are dynamic
				definite = False
				return

			# Specific outputs are specified by returning the tuple (<port name:str>, <value:Any>). All other formats of tuple are invalid.
			if isinstance(node.value, ast.Tuple):
				if len(node.value.elts) != 2:
					raise StructureInvalidTupleError(name, node.lineno, tuple(str(elt) for elt in node.value.elts))

				if isinstance(node.value.elts[0], ast.Constant):
					# No number/name translation for output ports
					if isinstance(node.value.elts[0].value, str):
						port_name = node.value.elts[0].value
						if port_name not in emits:
							emits.append(port_name)
						port_paths.setdefault(port_name, set()).add(path)
					else:
						raise StructureNonStrPortNameError(name, node.lineno, node.value.elts[0].value)
				else: # Dynamic output port names present
					definite = False
			elif not (isinstance(node.value, ast.Constant) and node.value.value is None):
				default = True

		def scan(node, path): # record every emit in one straight-line subtree at a fixed guarding-path
			for n in filter(lambda n: isinstance(n, (ast.Return, ast.Yield, ast.YieldFrom)), walk_ast(node)):
				record(n, path)

		def visit(stmts, path):
			for stmt in stmts:
				if isinstance(stmt, ast.If):
					scan(stmt.test, path)
					visit(stmt.body, path + ((id(stmt), 'then'),))
					visit(stmt.orelse, path + ((id(stmt), 'else'),))
				elif isinstance(stmt, (ast.For, ast.AsyncFor)):
					scan(stmt.iter, path)
					visit(stmt.body, path + ((id(stmt), 'loop'),)) # a loop body may run zero times, so its emits are conditional
					visit(stmt.orelse, path)
				elif isinstance(stmt, ast.While):
					scan(stmt.test, path)
					visit(stmt.body, path + ((id(stmt), 'loop'),))
					visit(stmt.orelse, path)
				elif isinstance(stmt, ast.Match):
					scan(stmt.subject, path)
					for i, case in enumerate(stmt.cases):
						visit(case.body, path + ((id(stmt), i),))
				elif isinstance(stmt, ast.Try):
					# An exception can pre-empt any statement in a try region, so each emit there is its own optional arm.
					for section in (stmt.body, *[ h.body for h in stmt.handlers ], stmt.orelse, stmt.finalbody):
						for sub in section:
							scan(sub, path + ((id(sub), 'try'),))
				elif isinstance(stmt, (ast.With, ast.AsyncWith)):
					visit(stmt.body, path)
				elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
					pass # nested scopes are not part of this method's emit surface
				else:
					scan(stmt, path)

		func = next((n for n in ast_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
		if func is not None:
			visit(func.body, ())

		# An empty path means an unconditional emit; several distinct paths means emitted under more than one guard. Neither belongs to a single arm.
		arms_map:dict[tuple, set[str]] = {}
		for port, paths in port_paths.items():
			if () in paths or len(paths) > 1:
				continue
			(only,) = tuple(paths)
			arms_map.setdefault(only, set()).add(port)

		return EmitInfo(emits, definite, default, [ frozenset(ports) for ports in arms_map.values() ])

	def resolve_arms(self, full_outputs:set[str], output_groups:dict|None) -> dict[str, frozenset[str]]:
		"""Combine this module's AST-derived arms with an optional ``output_groups`` declaration.

		Args:
			full_outputs: The node's complete set of output ports (wired outputs for dynamic emitters).
			output_groups: Declared arm mapping from the module class, or ``None``.

		Returns:
			Mapping from each conditional output port to its arm; unconditional ports are absent.
		"""

		ast_map = { port: arm for arm in self.arms for port in arm }

		if output_groups is None:
			if self.definite_emits:
				return ast_map
			# Dynamic emitter with no declaration: arms are undeterminable, so treat all outputs as one shared arm.
			log.warn('undetermined_arms', context='harness.module.arms', module=self.name)
			shared = frozenset(full_outputs)
			return { port: shared for port in full_outputs }

		og_map = { port: arm for arm in expand_output_groups(output_groups, full_outputs, self.name) for port in arm }

		# The declaration may not contradict what the AST could determine over the named ports.
		if partition_over(set(self.emits), ast_map) != partition_over(set(self.emits), og_map):
			log.fatal('output_groups_mismatch', context='harness.module.arms', module=self.name)

		return ast_map if self.definite_emits else og_map

def expand_output_groups(output_groups:dict, full_outputs:set[str], name:str) -> list[frozenset[str]]:
	"""Resolve a declared ``output_groups`` mapping into concrete arm port-sets.

	Args:
		output_groups: Declared mapping of group name to member port names, where a ``RestSentinel``
			member list means "all outputs not named in another group".
		full_outputs: The node's complete set of output ports (wired outputs for dynamic emitters).
		name: Module class name, used only for error reporting.

	Returns:
		One frozenset per group; ports named in no group (and not covered by ``REST``) are unconditional.
	"""

	explicit:dict[str, frozenset[str]] = {}
	rest_group = None
	named_union:set[str] = set()
	for group, members in output_groups.items():
		if isinstance(members, RestSentinel):
			if rest_group is not None:
				log.fatal('multiple_rest', context='harness.module.arms', module=name)
			rest_group = group
		else:
			member_set = frozenset(members)
			if len(named_union & member_set) > 0:
				log.fatal('overlapping_output_groups', context='harness.module.arms', module=name, ports=sorted(named_union & member_set))
			explicit[group] = member_set
			named_union |= member_set

	unknown = named_union - full_outputs
	if len(unknown) > 0:
		log.fatal('unknown_output_group_ports', context='harness.module.arms', module=name, ports=sorted(unknown))

	arms = list(explicit.values())
	if rest_group is not None and len(rest := frozenset(full_outputs - named_union)) > 0:
		arms.append(rest)
	return arms

def partition_over(ports:set[str], arm_map:dict[str, frozenset[str]]) -> tuple[frozenset[frozenset[str]], frozenset[str]]:
	"""Project an arm map onto a port subset, returning its arm grouping and unconditional set.

	Args:
		ports: The ports to project onto (the AST-known ports for a cross-check).
		arm_map: Mapping from port to its arm; ports absent from the map are unconditional.

	Returns:
		A ``(grouping of the ports by shared arm, ports with no arm)`` pair, comparable across sources.
	"""

	groups:dict[frozenset[str], set[str]] = defaultdict(set)
	always:set[str] = set()
	for port in ports:
		arm = arm_map.get(port)
		if arm is None:
			always.add(port)
		else:
			groups[arm].add(port)
	return frozenset(frozenset(members) for members in groups.values()), frozenset(always)
