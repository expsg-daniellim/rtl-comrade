import importlib.util
import inspect
import os
from pathlib import Path
import re
from serde import serde
from serde.yaml import from_yaml

CAMEL_CASE_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

@serde
class ModuleModuleConfig:
	class_name: str
	name: str | None

@serde
class ModuleFileConfig:
	name: str | None
	file: Path
	modules: list[ModuleModuleConfig] | None

@serde
class ModuleConfig:
	files: list[ModuleFileConfig]

class ModuleLoadException(Exception):
	def __init__(self, name, message):
		super.__init__(message)

	def __str__(self):
		return f"{self.name}: {self.message}"

def to_module_config(class_name:str) -> ModuleModuleConfig:
	name = CAMEL_CASE_RE.sub('_', class_name).lower()
	config = ModuleModuleConfig(class_name, name)
	return config

def load_module(config:ModuleFileConfig):
	module_name = Path(config.file).with_suffix('').as_posix().replace('/', '.') if config.name is None else config.name
	if not config.file.is_file():
		raise ModuleLoadException(module_name, f"{config.file} not found")

	spec = importlib.util.spec_from_file_location(module_name, config.file)
	module = importlib.util.module_from_spec(spec)

	if spec is None:
		raise ModuleLoadException(module_name, "spec could not be created")
	if spec.loader is None:
		raise ModuleLoadException(module_name, "spec has no loader")

	spec.loader.exec_module(module)
	available_mods = dict(inspect.getmembers(module, inspect.isclass))
	to_get = [ to_module_config(class_name) for class_name in available_mods ] if config.modules is None else config.modules
	res = {}
	for mod in to_get:
		if mod.class_name in available_mods:
			if mod.name in res:
				raise ModuleLoadException(module_name, f"duplicate module definition {mod.name}")
			res[mod.name] = available_mods[mod.class_name]
		else:
			raise ModuleLoadException(module_name, f"module {mod.name} class {mod.class_name} not found in {config.file}")

	return res

# Merges a into b, raising an error on duplicate keys
def merge_dict(a:dict, b:dict):
	for (key, val) in b.items():
		if key in a:
			raise ValueError(f"duplicate key {key}")
		else:
			a[key] = val

def load_module_folder(path:str):
	folder_path = Path(path)
	config = None

	if os.path.isfile(folder_path / "config.yaml"):
		with open(folder_path / "config.yaml", 'r') as file:
			config = from_yaml(ModuleConfig, file.read())
			for file in config.files:
				file.file = folder_path / file.file
	else:
		files = [ ModuleFileConfig(None, file, None) for file in filter(lambda p: os.path.isfile(p) and p.suffix == '.py', map(lambda p: folder_path / p, os.listdir(folder_path))) ]
		config = ModuleConfig(files)

	res = {}
	for file_config in config.files:
		merge_dict(res, load_module(file_config))

	return res

def load_module_folders(paths:list[str]):
	res = {}
	for path in paths:
		merge_dict(res, load_module_folder(path))

	return res
