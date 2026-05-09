import ast
from collections import deque
from dataclasses import dataclass
import inspect
from inspect import Parameter
import structlog
import textwrap
import typing

log = structlog.get_logger()

# BFS of the AST filtering out nested function nodes
def walk_ast(node):
	queue = deque([node])
	passedTop = False # Keep tracking of passing the top-level function node
	while queue:
		n = queue.popleft()
		if not (isinstance(n, ast.FunctionDef) or isinstance(n, ast.Lambda) or isinstance(n, ast.AsyncFunctionDef)):
			queue.extend(ast.iter_child_nodes(n))
		elif not passedTop:
			passedTop = True
			queue.extend(ast.iter_child_nodes(n))

		yield n

@dataclass(frozen=True, slots=True)
class StructureInvalidTupleError(Exception):
	name: str
	tuple_: tuple

@dataclass(frozen=True, slots=True)
class StructureNonStrPortNameError(Exception):
	name: str
	port_name: typing.Any

@dataclass(frozen=True, slots=True)
class ModuleStructureArg:
	name: str
	type_: str | None = None
	has_default: bool = False
	default: typing.Any = None

@dataclass
class ModuleStructure:
	args: list[ModuleStructureArg]
	emits: list[str]
	definite_emits: bool

	def __init__(self, Module):
		# Assume that Module has been pre-validated to have run

		# Populate args from the function signature
		try:
			sig = inspect.signature(Module.run)
		except (TypeError, ValueError) as e:
			log.fatal('unavailable_signature', exc_info=e)

		self.args = [ ModuleStructureArg(name=name, type_=str(param.annotation) if param.annotation != Parameter.empty else None, has_default=param.default != Parameter.empty, default=param.default if param.default != Parameter.empty else None) for (name, param) in sig.parameters.items() if name != 'self' ]

		# Parse AST in steps to catch individual Exceptions from each step
		try:
			src = textwrap.dedent(inspect.getsource(Module.run))
		except OSError as e:
			log.fatal('file_unavailable', errno=e.errno)
		except TypeError as e:
			log.fatal('unloadable', message=str(e))
		except ValueError as e:
			log.fatal('wrapped_cycle')

		try:
			ast_tree = ast.parse(src)
		except SyntaxError as e:
			log.fatal('syntax_error', filename=e.filename, lineno=e.lineno, offset=e.offset, text=e.text, end_lineno=e.end_lineno, end_offset=e.end_offset)
		except ValueError as e:
			log.fatal('value_error', message=str(e))
		except TypeError as e:
			log.fatal('type_error', message=str(e))
		except MemoryError as e:
			log.fatal('memory_error', message=str(e))
		except RecursionError as e:
			log.fatal('recursion_err', message=str(e))

		# Populate emits by walking through source code and inferring likely behaviour from yields/returns
		self.emits = []
		default = False
		self.definite_emits = True
		for node in filter(lambda node: isinstance(node, ast.Return) or isinstance(node, ast.Yield), walk_ast(ast_tree)):
			# Specific outputs are specified by returning the tuple (<port name:str>, <value:Any>). All other formats of tuple are invalid.
			if isinstance(node.value, ast.Tuple):
				if len(node.value.elts) != 2:
					raise StructureInvalidTupleError(Module.__name__, node.value.elts)

				if isinstance(node.value.elts[0], ast.Constant):
					# No number/name translation for output ports
					if isinstance(node.value.elts[0].value, str):
						self.emits.append(str(node.value.elts[0].value))
					else:
						raise StructureNonStrPortNameError(Module.__name__, node.value.elts[0].value)
				else: # Dynamic output port names present
					self.definite_emits = False
			elif not (isinstance(node.value, ast.Constant) and node.value.value is None):
				default = True

		if default:
			self.emits.insert(0, 'default')
