import ast
from collections import deque
from dataclasses import dataclass
import inspect
from inspect import Parameter
import textwrap
import typing

def walk_ast(node):
	queue = deque([node])
	passedTop = False
	while queue:
		n = queue.popleft()
		if not (isinstance(n, ast.FunctionDef) or isinstance(n, ast.Lambda) or isinstance(n, ast.AsyncFunctionDef)):
			queue.extend(ast.iter_child_nodes(n))
		elif not passedTop:
			passedTop = True
			queue.extend(ast.iter_child_nodes(n))

		yield n

class StructureError(Exception):
	def __init__(self, name, message):
		super().__init__(message)
		self.name = name
		self.message = message

	def __str__(self):
		return f"{self.name}: {self.message}"

@dataclass
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
		if not hasattr(Module, 'run'):
			raise StructureError(Module.__name__, "no function 'run' available")

		sig = inspect.signature(Module.run)
		self.args = [ ModuleStructureArg(name=name, type_=param.annotation.__name__ if param.annotation != Parameter.empty else None, has_default=param.default != Parameter.empty, default=param.default if param.default != Parameter.empty else None) for (name, param) in sig.parameters.items() if name != 'self' ]

		self.emits = []
		default = False
		self.definite_emits = True
		for node in filter(lambda node: isinstance(node, ast.Return) or isinstance(node, ast.Yield), walk_ast(ast.parse(textwrap.dedent(inspect.getsource(Module.run))))):
			if isinstance(node.value, ast.Tuple):
				if len(node.value.elts) != 2:
					# TODO: better error handling
					raise StructureError(Module.__name__, "invalid return tuple")

				if isinstance(node.value.elts[0], ast.Constant):
					# No number/name translation for output ports
					if isinstance(node.value.elts[0], str):
						self.emits.append(str(node.value.elts[0].value))
					else:
						raise StructureError(Module.__name__, "non-str return port name")
				else: # Dynamic output port names present
					self.definite_emits = False
			else:
				default = True

		if default:
			self.emits.insert(0, 'default')
