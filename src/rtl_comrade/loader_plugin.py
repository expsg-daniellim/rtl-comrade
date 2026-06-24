"""Plugin discovery and import: resolving configured paths into plugin classes."""

from __future__ import annotations
from dataclasses import dataclass
import inspect
import os
from pathlib import Path
import re
from typing import cast, Any, Self

from serde import serde
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars

from .logging import HarnessLogger
from .loader_utils import import_plugin_file, load_config_file

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())

# Camel case to snake case.
CAMEL_CASE_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

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

	@classmethod
	def from_class_name(cls, class_name:str) -> Self:
		"""Create a default exported plugin mapping from a class name.

		Args:
			class_name: Python class name to convert into a default plugin name.

		Returns:
			A PluginModuleConfig with a snake_case exported plugin name.
		"""

		name = CAMEL_CASE_RE.sub('_', class_name).lower()
		return cls(class_name, name)

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

	def load(self, namespace:str='') -> dict:
		"""Dynamically import this plugin file and return its exported class mappings.

		Returns:
			Mapping from exported plugin name to loaded Python class.
		"""

		# import_plugin_file leaves the plugin/file logging context bound for the selection below
		module = import_plugin_file(self.file, self.name, namespace)
		try:
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

def load_plugin_config(path:Path, relative_path:Path=Path()) -> list[PluginFileConfig]:
	"""Resolve one configured path into a list of plugin file configs without loading.

	Args:
		path: Path to a Python file or plugin directory.

	Returns:
		Plugin file configs discovered under path, deduplicated by resolved file path.
	"""

	path = relative_path / path

	bind_contextvars(context='harness.load.path', file=str(path))
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

def load_plugin_configs(paths:list[Path], relative_path:Path=Path()) -> list[PluginFileConfig]:
	"""Resolve multiple configured paths into a flat list of plugin file configs.

	Args:
		paths: Plugin file or directory paths to resolve.

	Returns:
		Flat list of plugin file configs from all paths, with duplicate paths skipped.
	"""

	result = []
	seen: set[Path] = set()
	for path in paths:
		if path not in seen:
			seen.add(path)
			result.extend(load_plugin_config(path, relative_path))

	return result

def load_plugins(configs:list[PluginFileConfig], namespace:str='') -> dict[str, type[Any]]:
	"""Load and merge plugins from a list of resolved plugin file configs.

	Args:
		configs: Plugin file configs to load.

	Returns:
		Merged mapping from exported plugin name to loaded Python class.
	"""

	# Load each file and then merge into a single map
	res = {}
	for config in configs:
		for (name, plugin) in config.load(namespace).items():
			if name in res:
				log.fatal('duplicate_definition', context='harness.load.plugins', file=str(config.file), key=name)
			else:
				res[name] = plugin
	return res
