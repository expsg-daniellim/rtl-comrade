from dataclasses import dataclass
import importlib.util
import inspect
import os
from pathlib import Path
import re
from serde import serde
from serde.yaml import from_yaml
import sys

# Camel case to snake case
CAMEL_CASE_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Define individual error types
@dataclass
class LoadError(Exception):
	plugin: str|None
	file: str

@dataclass
class LoadFileNotFoundError(LoadError):
	pass

class LoadInvalidSpecError(LoadError):
	pass

class LoadSpecNoLoaderError(LoadError):
	pass

@dataclass
class LoadDuplicateDefinitionError(LoadError):
	key: str

@dataclass
class LoadMissingClassError(LoadError):
	module_name: str
	class_name: str

# Config file types
@serde
class PluginModuleConfig:
	class_name: str
	name: str | None

	@staticmethod
	def from_class_name(class_name:str) -> PluginModuleConfig:
		name = CAMEL_CASE_RE.sub('_', class_name).lower()
		return PluginModuleConfig(class_name, name)

@serde
class PluginFileConfig:
	name: str | None
	file: Path
	type_: str | None
	plugins: list[PluginModuleConfig] | None

@serde
class PluginConfig:
	files: list[PluginFileConfig]

# Actual load functions. Hierarchy: load_files -> load_file -> load_plugin
def load_plugin(config:PluginFileConfig):
	# Name plugin file based on file path without extension
	plugin_name = Path(config.file).with_suffix('').as_posix().replace('/', '.') if config.name is None else config.name

	# Validate plugin file existence
	if not config.file.is_file():
		raise LoadFileNotFoundError(plugin_name, config.file)

	# Do dynamic import of plugin file
	spec = importlib.util.spec_from_file_location(plugin_name, config.file)
	if spec is None:
		raise LoadInvalidSpecError(plugin_name, config.file)

	module = importlib.util.module_from_spec(spec)
	if spec.loader is None:
		raise LoadSpecNoLoaderError(plugin_name, config.file)

	# Add module to sys.modules so its source can be inspected later
	sys.modules[plugin_name] = module
	# Load module
	spec.loader.exec_module(module)

	# Available classes in file
	available_mods = dict(inspect.getmembers(module, inspect.isclass))
	# Assume all classes are intended to be loaded in absence of config file
	to_get = [ PluginModuleConfig.from_class_name(class_name) for class_name in available_mods ] if config.plugins is None else config.plugins
	res = {}
	for mod in to_get:
		if mod.class_name in available_mods:
			# Don't silently overwrite available mappings
			if mod.name in res:
				raise LoadDuplicateDefinitionError(plugin_name, config.file, mod.name)
			res[mod.name] = available_mods[mod.class_name]
		else:
			raise LoadMissingClassError(plugin_name, config.file, mod.name, mod.class_name)

	return res

# Merges a into b, raising an error on duplicate keys
def merge_dict(a:dict, b:dict):
	for (key, val) in b.items():
		if key in a:
			raise ValueError(f"duplicate key {key}")
		else:
			a[key] = val

def load_path(path:str) -> dict:
	path = Path(path)
	config = None

	if not path.exists():
		raise LoadFileNotFoundError(None, path)

	if os.path.isfile(path): # Load directly if path is a file and not a dir
		files = [PluginFileConfig(None, path, None, None)]
		config = PluginConfig(files)
	elif os.path.isfile(path / "config.yaml"): # Check for a config.yaml in dir
		with open(path / "config.yaml", 'r') as file:
			config = from_yaml(PluginConfig, file.read())
			for file in config.files:
				file.file = path / file.file # Make path relative to script
	else:
		# Recreate a dummy PluginFileConfig without any of the specifics
		files = [ PluginFileConfig(None, file, None, None) for file in filter(lambda p: os.path.isfile(p) and p.suffix == '.py', map(lambda p: path / p, os.listdir(path))) ]
		config = PluginConfig(files)

	# Load each file and then merge into a single map
	res = {}
	for file_config in config.files:
		file_plugins = load_plugin(file_config)
		for (name, plugin) in file_plugins.items():
			if name in res:
				raise LoadDuplicateDefinitionError(str(path), file_config.file, name)
			else:
				res[name] = plugin

	return res

def load_paths(paths:list[str]) -> dict:
	res = {}
	for path in paths:
		file_plugins = load_path(path)
		for (name, plugin) in file_plugins.items():
			if name in res:
				raise LoadDuplicateDefinitionError(None, path, name)
			else:
				res[name] = plugin

	return res
