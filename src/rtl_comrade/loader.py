"""Graph-config loading plus plugin discovery and dynamic import."""

from __future__ import annotations
from dataclasses import dataclass
import importlib.util
import inspect
import os
from pathlib import Path
import re
import sys
from typing import cast, Any, Never

from serde import serde, SerdeError
from serde.yaml import from_yaml
from yaml.error import MarkedYAMLError
from yaml.reader import ReaderError
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .logging import HarnessLogger

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

# Camel case to snake case.
CAMEL_CASE_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Helper to have a common place to catch/log config file errors.
def load_config_file(Config, path:Path):
	"""Load one YAML config file into a serde-backed type.

	Args:
		Config: Target serde type to deserialize into.
		path: Filesystem path to the YAML file.

	Returns:
		The deserialized config object.
	"""

	try:
		with open(path, 'r', encoding='utf-8') as file:
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

	return Never  # pragma: no cover

@serde
@dataclass(slots=True, frozen=True)
class PluginModuleConfig:
	"""One exported class mapping within a plugin file manifest.

	Attributes:
		class_name: Python class name to load from the module file.
		name: Public plugin name exposed to graph configuration.
	"""

	class_name: str
	name: str | None

	@staticmethod
	def from_class_name(class_name:str) -> PluginModuleConfig:
		"""Create a default exported plugin mapping from a class name.

		Args:
			class_name: Python class name to convert into a default plugin name.

		Returns:
			A PluginModuleConfig with a snake_case exported plugin name.
		"""

		name = CAMEL_CASE_RE.sub('_', class_name).lower()
		return PluginModuleConfig(class_name, name)

@serde
@dataclass(slots=True)
class PluginFileConfig:
	"""One plugin-file entry inside a plugin folder manifest.

	Attributes:
		name: Optional module-import name override for the file.
		file: Relative or absolute path to the plugin Python file.
		type_: Reserved manifest field currently carried through unchanged.
		plugins: Optional exported class mappings for this file.
	"""

	name: str | None
	file: Path
	type_: str | None
	plugins: list[PluginModuleConfig] | None

	def load(self) -> dict:
		"""Dynamically import this plugin file and return its exported class mappings.

		Returns:
			Mapping from exported plugin name to loaded Python class.
		"""

		# Allow plugin files to import siblings via Python's normal import machinery
		file_dir = self.file.parent.resolve()
		sys_path_entry = str(file_dir.parent if (file_dir / '__init__.py').exists() else file_dir)
		if sys_path_entry not in sys.path:
			sys.path.insert(0, sys_path_entry)

		# Name plugin file based on file path without extension
		plugin_name = Path(self.file).with_suffix('').as_posix().replace('/', '.') if self.name is None else self.name

		# Bind some logging context
		bind_contextvars(plugin=plugin_name, file=str(self.file))
		try:
			# Validate plugin file existence
			if not self.file.is_file():
				log.fatal('not_found')

			# Do dynamic import of plugin file
			spec = importlib.util.spec_from_file_location(plugin_name, self.file)
			if spec is None:
				log.fatal('spec.invalid')

			if spec.loader is None:
				log.fatal('spec.no_loader')

			# Canonical name Python's machinery assigns; packages only — plain-dir stems collide with stdlib (e.g. "io").
			plugin_file_dir = self.file.parent.resolve()
			if (plugin_file_dir / '__init__.py').exists():
				try:
					canonical_name = self.file.resolve().relative_to(str(plugin_file_dir.parent)).with_suffix('').as_posix().replace('/', '.')
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

			available_mods = dict(inspect.getmembers(module, inspect.isclass))

			# Auto-discovery: exclude imported classes (foreign __module__) to avoid duplicate_definition.
			to_get = [ PluginModuleConfig.from_class_name(n) for n, cls in available_mods.items() if cls.__module__ == module.__name__ ] if self.plugins is None else self.plugins
			res = {}
			for mod in to_get:
				if mod.class_name in available_mods:
					# Don't silently overwrite available mappings
					if mod.name in res:
						log.fatal('duplicate_key', key=mod.name)
					res[mod.name] = available_mods[mod.class_name]
				else:
					log.fatal('missing_class', module=mod.name, class_name=mod.class_name)
		finally:
			unbind_contextvars('plugin', 'file')

		return res

@serde
class PluginConfig:
	"""Top-level manifest describing one plugin file collection.

	Attributes:
		files: Plugin-file entries to load from this manifest.
	"""

	files: list[PluginFileConfig]

# Actual load functions. Hierarchy: load_file_configs -> config.load(); load_paths -> load_path -> load_file_configs -> config.load().
def resolve_path(path:Path) -> list[PluginFileConfig]:
	"""Resolve one configured path into a list of plugin file configs without loading.

	Args:
		path: Path to a Python file or plugin directory.

	Returns:
		Plugin file configs discovered under path, deduplicated by resolved file path.
	"""

	bind_contextvars(file=str(path))
	if not path.exists():
		log.fatal('not_found', file=str(path))

	try:
		if os.path.isfile(path): # Load directly if path is a file and not a dir
			files = [PluginFileConfig(None, path, None, None)]
		elif os.path.isfile(path / "config.yaml"): # Check for a config.yaml in dir
			plugin_config = load_config_file(PluginConfig, path / 'config.yaml') # Let exceptions bubble up
			for file_config in plugin_config.files:
				file_config.file = path / file_config.file # Make path relative to script
			files = plugin_config.files
		else:
			# Recreate a dummy PluginFileConfig without any of the specifics
			files = [ PluginFileConfig(None, p, None, None) for p in filter(lambda p: os.path.isfile(p) and p.suffix == '.py', map(lambda p: path / p, os.listdir(path))) ]
	except UnicodeDecodeError as e:
		log.fatal('invalid_unicode', file=str(path), reason=e.reason, invalid_slice=e.object[e.start:e.end].decode(encoding=e.encoding or 'utf-8', errors='replace'), exc_info=e)
	except FileNotFoundError as e:
		log.fatal('not_found', file=str(path), exc_info=e)
	except IsADirectoryError as e:
		log.fatal('is_directory', file=str(path), exc_info=e)
	except PermissionError as e:
		log.fatal('permission_denied', file=str(path), exc_info=e)
	except OSError as e:
		log.fatal('os_error', file=str(path), err=e.strerror, errno=e.errno, exc_info=e)
	finally:
		unbind_contextvars('file')

	seen: set[Path] = set()
	result = []
	for f in files:
		resolved = f.file.resolve()
		if resolved not in seen:
			seen.add(resolved)
			result.append(f)
	return result

def resolve_paths(paths:list[str]) -> list[PluginFileConfig]:
	"""Resolve multiple configured path strings into a flat list of plugin file configs.

	Args:
		paths: Plugin file or directory paths to resolve.

	Returns:
		Flat list of plugin file configs from all paths, with duplicate path strings skipped.
	"""

	result = []
	seen: set[str] = set()
	for path in paths:
		if path not in seen:
			seen.add(path)
			result.extend(resolve_path(Path(path)))

	return result

def load_file_configs(configs:list[PluginFileConfig]) -> dict:
	"""Load and merge plugins from a list of resolved plugin file configs.

	Args:
		configs: Plugin file configs to load.

	Returns:
		Merged mapping from exported plugin name to loaded Python class.
	"""

	# Load each file and then merge into a single map
	res = {}
	for config in configs:
		for (name, plugin) in config.load().items():
			if name in res:
				log.fatal('duplicate_definition', file=str(config.file), key=name)
			else:
				res[name] = plugin
	return res

def load_path(path:Path) -> dict:
	"""Load every plugin exported from one configured path.

	Args:
		path: Path to a Python file or plugin directory.

	Returns:
		Mapping from exported plugin name to loaded Python class.
	"""

	return load_file_configs(resolve_path(path))

def load_paths(paths:list[Path]) -> dict:
	"""Load and merge plugins from multiple configured paths.

	Args:
		paths: Plugin file or directory paths to load.

	Returns:
		Merged mapping from exported plugin name to loaded Python class.
	"""

	res = {}
	for path in paths:
		file_plugins = load_path(path)
		for (name, plugin) in file_plugins.items():
			if name in res:
				log.fatal('duplicate_definition', file=path, key=name)
			else:
				res[name] = plugin

	return res
