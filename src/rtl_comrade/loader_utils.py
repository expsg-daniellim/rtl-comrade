"""Shared loader helpers: YAML config-file loading and dynamic plugin-file import."""

from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import cast, Any, Never

from serde import SerdeError
from serde.yaml import from_yaml
from yaml.error import MarkedYAMLError
from yaml.reader import ReaderError
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

# Helper to have a common place to catch/log config file errors.
def load_config_file(Config, path:Path, parent:Path=Path()):
	"""Load one YAML config file into a serde-backed type.

	Args:
		Config: Target serde type to deserialize into.
		path: Filesystem path to the YAML file.

	Returns:
		The deserialized config object.
	"""

	bind_contextvars(context='harness.load.config')
	try:
		with open(parent / path, 'r', encoding='utf-8') as file:
			config = from_yaml(Config, file.read())
			return config
	except UnicodeDecodeError as e:
		log.fatal('invalid_unicode', reason=e.reason, invalid_slice=e.object[e.start:e.end].decode(encoding=e.encoding or 'utf-8', errors='replace'), exc_info=e)
	except FileNotFoundError as e:
		log.fatal('not_found', exc_info=e)
	except IsADirectoryError as e:
		log.fatal('is_directory', exc_info=e)
	except PermissionError as e:
		log.fatal('permission_denied', exc_info=e)
	except OSError as e:
		log.fatal('os_error', err=e.strerror, errno=e.errno, exc_info=e)
	except SerdeError as e:
		log.fatal('serde_error', message=str(e), exc_info=e)
	except MarkedYAMLError as e:
		mark_fields:dict[str, Any] = {}
		if e.problem_mark is not None:
			mark_fields['problem_name'] = e.problem_mark.name
			mark_fields['index'] = e.problem_mark.index
			mark_fields['line'] = e.problem_mark.line
			mark_fields['column'] = e.problem_mark.line
			mark_fields['pointer'] = e.problem_mark.pointer

		log.fatal('yaml.marked', problem=e.problem, **mark_fields,  exc_info=e)
	except ReaderError as e:
		log.fatal('yaml.reader', error_name=e.name, position=e.position, character=e.character, encoding=e.encoding, reason=e.reason, exc_info=e)
	finally:
		unbind_contextvars('context')

	return Never  # pragma: no cover

def import_plugin_file(file:Path, name:str | None, namespace:str) -> ModuleType:
	"""Dynamically import one plugin Python file and return its module object.

	Leaves the plugin/file logging context bound on return so callers can attach
	their own member-selection diagnostics to it.

	Args:
		file: Filesystem path to the plugin Python file.
		name: Optional module-import name override for the file.
		namespace: Category scope prefixed onto the override name in sys.modules.

	Returns:
		The imported module object.
	"""

	# Allow plugin files to import siblings via Python's normal import machinery
	file_dir = file.parent.resolve()
	sys_path_entry = str(file_dir.parent if (file_dir / '__init__.py').exists() else file_dir)
	if sys_path_entry not in sys.path:
		sys.path.insert(0, sys_path_entry)

	# Name plugin file based on file path without extension
	plugin_name = file.with_suffix('').as_posix().replace('/', '.') if name is None else f'{namespace}.{name}'

	# Bind some logging context
	bind_contextvars(context='harness.load.plugin', plugin=plugin_name, file=str(file))

	# Validate plugin file existence
	if not file.is_file():
		log.fatal('not_found')

	# Do dynamic import of plugin file
	spec = importlib.util.spec_from_file_location(plugin_name, file)
	if spec is None:
		log.fatal('spec.invalid')

	if spec.loader is None:
		log.fatal('spec.no_loader')

	# Canonical name Python's machinery assigns; packages only — plain-dir stems collide with stdlib (e.g. "io").
	plugin_file_dir = file.parent.resolve()
	if (plugin_file_dir / '__init__.py').exists():
		try:
			canonical_name = file.resolve().relative_to(str(plugin_file_dir.parent)).with_suffix('').as_posix().replace('/', '.')
		except ValueError:
			canonical_name = None
	else:
		canonical_name = None

	# Reuse if already loaded (e.g. as a transitive import); re-executing splits class identity.
	if canonical_name is not None and canonical_name in sys.modules:
		module = sys.modules[canonical_name]
	elif plugin_name in sys.modules:
		module = sys.modules[plugin_name]
	else:
		# All possible exceptions should have been covered by None checking, explicit string plugin_name and using spec_from_file_location
		module = importlib.util.module_from_spec(spec)
		sys.modules[plugin_name] = module  # register before exec: needed for circular imports and inspect.getsource()
		try:
			spec.loader.exec_module(module)
		except UnicodeDecodeError as e:
			log.fatal('invalid_unicode', reason=e.reason, invalid_slice=e.object[e.start:e.end].decode(encoding=e.encoding or 'utf-8', errors='replace'), exc_info=e)
		except FileNotFoundError as e:
			log.fatal('not_found', exc_info=e)
		except IsADirectoryError as e:
			log.fatal('is_directory', exc_info=e)
		except PermissionError as e:
			log.fatal('permission_denied', exc_info=e)
		except OSError as e:
			log.fatal('os_error', err=e.strerror, errno=e.errno, exc_info=e)
		except SyntaxError as e:
			log.fatal('syntax_error', filename=e.filename, lineno=e.lineno, offset=e.offset, text=e.text, end_lineno=e.end_lineno, end_offset=e.end_offset, exc_info=e)
		except ValueError as e:
			log.fatal('value_error', message=str(e), exc_info=e)
		except TypeError as e:
			log.fatal('type_error', message=str(e), exc_info=e)
		except ModuleNotFoundError as e:
			log.fatal('module_not_found', exc_info=e)
		except ImportError as e:
			log.fatal('import_error', module_name=e.name, module_path=e.path, exc_info=e)
		except Exception as e:
			log.fatal('exception', exc_info=e)

	return module
