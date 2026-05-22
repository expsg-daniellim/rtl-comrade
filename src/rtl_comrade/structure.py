"""Static analysis of module signatures and emitted output-port names."""

import ast
from collections import deque
from dataclasses import dataclass
import inspect
from inspect import Parameter
import textwrap
import typing

import structlog
from typing import cast

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

@dataclass(slots=True)
class ModuleStructure:
	"""Statically inferred view of one module's input and output surface.

	Attributes:
		args: Ordered input arguments inferred from ``run(...)``.
		emits: Statically known output-port names.
		definite_emits: Whether ``emits`` is believed to be complete.
	"""

	args: list[ModuleStructureArg]
	emits: list[str]
	definite_emits: bool

	def __init__(self, Module):
		"""Analyze one module class and infer its runtime structure.

		Args:
			Module: Module plugin class whose ``run(...)`` method should be inspected.

		Returns:
			None.
		"""

		# Assume that Module has been pre-validated to have run.

		# Populate args from the function signature
		try:
			sig = inspect.signature(Module.run)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', exc_info=e)

		self.args = [ ModuleStructureArg(
			name=name,
			type_=str(param.annotation) if param.annotation != Parameter.empty else None,
			has_default=param.default != Parameter.empty,
		) for (name, param) in sig.parameters.items() if name != 'self' ]

		# Parse AST in steps to catch individual Exceptions from each step
		try:
			src = textwrap.dedent(inspect.getsource(Module.run))
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

		# Populate emits by walking through source code and inferring likely behaviour from yields/returns
		self.emits = []
		default = False
		self.definite_emits = True
		for node in filter(lambda node: isinstance(node, (ast.Return, ast.Yield)), walk_ast(ast_tree)):
			# Specific outputs are specified by returning the tuple (<port name:str>, <value:Any>). All other formats of tuple are invalid.
			if isinstance(node.value, ast.Tuple):
				if len(node.value.elts) != 2:
					raise StructureInvalidTupleError(Module.__name__, node.lineno, tuple(str(elt) for elt in node.value.elts))

				if isinstance(node.value.elts[0], ast.Constant):
					# No number/name translation for output ports
					if isinstance(node.value.elts[0].value, str):
						port_name = node.value.elts[0].value
						if port_name not in self.emits:
							self.emits.append(port_name)
					else:
						raise StructureNonStrPortNameError(Module.__name__, node.lineno, node.value.elts[0].value)
				else: # Dynamic output port names present
					self.definite_emits = False
			elif not (isinstance(node.value, ast.Constant) and node.value.value is None):
				default = True

		if default:
			self.emits.insert(0, 'default')
