import importlib.util
import inspect
import os
from pathlib import Path
from serde import serde
from serde.yaml import from_yaml

@serde
class ModuleModuleConfig:
	class_name: str
	name: str | None

@serde
class ModuleFileConfig:
	name: str | None
	file: str
	modules: list[ModuleModuleConfig] | None

@serde
class ModuleConfig:
	files: list[ModuleFileConfig]

class ModuleLoadException(Exception):
	pass

def to_module_config(class_name:str) -> ModuleModuleConfig:
	name = class_name # TODO: fancy CamelCase to snake_case conversion
	config = ModuleModuleConfig(class_name, name)
	return config

def load_module(folder:Path, config:ModuleFileConfig):
	# TODO: include full path as module name
	module_name = Path(config.file).stem if config.name is None else config.name
	spec = importlib.util.spec_from_file_location(module_name, folder / config.file)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)

	available_mods = dict(inspect.getmembers(module, inspect.isclass))
	to_get = [ to_module_config(class_name) for class_name in available_mods ] if config.modules is None else config.modules
	res = {}
	for mod in to_get:
		if mod.class_name in available_mods:
			if mod.name in res:
				raise ModuleLoadException(f"duplicate module definition {mod.name}")
			res[mod.name] = available_mods[mod.class_name]
		else:
			raise ModuleLoadException(f"module {mod.name} class {mod.class_name} not found in {config.file}")

	return res

def load_module_folder(path:str):
	folder_path = Path(path)
	config = None

	# TODO: expand folder_path into module paths
	if os.path.isfile(folder_path / "config.yaml"):
		with open(folder_path / "config.yaml", 'r') as file:
			config = from_yaml(ModuleConfig, file.read())
	else:
		files = [ ModuleFileConfig(None, file, None) for file in filter(lambda p: Path(p).suffix == '.py', filter(lambda p: os.path.isfile(folder_path / p), os.listdir(folder_path)))]
		config = ModuleConfig(files)

	res = {}
	for file_config in config.files:
		# TODO: check for duplicates in res
		res |= load_module(folder_path, file_config)

	return res
