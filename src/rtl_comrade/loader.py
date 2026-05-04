import importlib.util
import inspect
import os
from pathlib import Path
import re
from serde import serde
from serde.yaml import from_yaml
import sys

CAMEL_CASE_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

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

class LoadException(Exception):
	def __init__(self, name, message):
		super().__init__(message)
		self.name = name
		self.message = message

	def __str__(self):
		return f"{self.name}: {self.message}"

def load_plugin(config:PluginFileConfig):
	plugin_name = Path(config.file).with_suffix('').as_posix().replace('/', '.') if config.name is None else config.name
	if not config.file.is_file():
		raise LoadException(plugin_name, f"{config.file} not found")

	spec = importlib.util.spec_from_file_location(plugin_name, config.file)
	if spec is None:
		raise LoadException(plugin_name, "spec could not be created")

	module = importlib.util.module_from_spec(spec)
	if spec.loader is None:
		raise LoadException(plugin_name, "spec has no loader")

	sys.modules[plugin_name] = module
	spec.loader.exec_module(module)
	available_mods = dict(inspect.getmembers(module, inspect.isclass))
	to_get = [ PluginModuleConfig.from_class_name(class_name) for class_name in available_mods ] if config.plugins is None else config.plugins
	res = {}
	for mod in to_get:
		if mod.class_name in available_mods:
			if mod.name in res:
				raise LoadException(plugin_name, f"duplicate module definition {mod.name}")
			res[mod.name] = available_mods[mod.class_name]
		else:
			raise LoadException(plugin_name, f"module {mod.name} class {mod.class_name} not found in {config.file}")

	return res

# Merges a into b, raising an error on duplicate keys
def merge_dict(a:dict, b:dict):
	for (key, val) in b.items():
		if key in a:
			raise ValueError(f"duplicate key {key}")
		else:
			a[key] = val

# TODO: load file directly if file
def load_folder(path:str) -> dict:
	folder_path = Path(path)
	config = None

	if os.path.isfile(folder_path / "config.yaml"):
		with open(folder_path / "config.yaml", 'r') as file:
			config = from_yaml(PluginConfig, file.read())
			for file in config.files:
				file.file = folder_path / file.file
	else:
		files = [ PluginFileConfig(None, file, None) for file in filter(lambda p: os.path.isfile(p) and p.suffix == '.py', map(lambda p: folder_path / p, os.listdir(folder_path))) ]
		config = PluginConfig(files)

	res = {}
	for file_config in config.files:
		merge_dict(res, load_plugin(file_config))

	return res

def load_folders(paths:list[str]) -> dict:
	res = {}
	for path in paths:
		merge_dict(res, load_folder(path))

	return res
