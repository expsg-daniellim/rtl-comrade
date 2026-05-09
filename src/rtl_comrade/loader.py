from dataclasses import dataclass
import importlib.util
import inspect
import os
from pathlib import Path
import re
from serde import serde, SerdeError
from serde.yaml import from_yaml
from yaml.error import Mark, MarkedYAMLError
from yaml.reader import ReaderError
import structlog
from structlog.contextvars import bind_contextvars, unbind_contextvars
import sys

log = structlog.get_logger()

# Camel case to snake case
CAMEL_CASE_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Helper to have a common place to catch/log config file errors
def load_config_file(Config, path:Path):
	try:
		with open(path, 'r') as file:
			config = from_yaml(Config, file.read())
			return config
	except UnicodeDecodeError as e:
		log.fatal('invalid_unicode', reason=e.reason, invalid_slice=e.object[e.start:e.end])
	except FileNotFoundError as e:
		log.fatal('not_found')
	except IsADirectoryError as e:
		log.fatal('is_directory')
	except PermissionError as e:
		log.fatal('permission_denied')
	except OSError as e:
		log.fatal('os_error', errno=e.errno)
	except SerdeError as e:
		log.fatal('serde_error', message=str(e))
	except MarkedYAMLError as e:
		log.fatal('yaml.marked', problem=e.problem, problem_mark=e.problem_mark)
	except ReaderError as e:
		log.fatal('yaml.reader', error_name=e.name, position=e.position, character=e.character, encoding=e.encoding, reason=e.reason)

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

	# Bind some logging context
	bind_contextvars(plugin=plugin_name, file=config.file)

	# Validate plugin file existence
	if not config.file.is_file():
		log.fatal('not_found')

	# Do dynamic import of plugin file
	spec = importlib.util.spec_from_file_location(plugin_name, config.file)
	if spec is None:
		log.fatal('spec.invalid')
	
	if spec.loader is None:
		log.fatal('spec.no_loader')

	# All possible exceptions should have been covered by None checking, explicit string plugin_name and using spec_from_file_location
	module = importlib.util.module_from_spec(spec)

	# Add module to sys.modules so its source can be inspected later
	sys.modules[plugin_name] = module
	# Load module
	try:
		spec.loader.exec_module(module)
	except UnicodeDecodeError as e:
		log.fatal('invalid_unicode', reason=e.reason, invalid_slice=e.object[e.start:e.end])
	except FileNotFoundError as e:
		log.fatal('not_found')
	except IsADirectoryError as e:
		log.fatal('is_directory')
	except PermissionError as e:
		log.fatal('permission_denied')
	except OSError as e:
		log.fatal('os_error', errno=e.errno)
	except SyntaxError as e:
		log.fatal('syntax_error', **e)
	except ValueError as e:
		log.fatal('value_error', message=str(e))
	except TypeError as e:
		log.fatal('type_error', message=str(e))
	except ModuleNotFoundError as e:
		log.fatal('module_not_found')
	except ImportError as e:
		log.fatal('import_error', module_name=e.name, module_path=e.path)
	except Exception as e:
		log.fatal('exception', exc_info=e)

	# Available classes in file
	available_mods = dict(inspect.getmembers(module, inspect.isclass))
	# Assume all classes are intended to be loaded in absence of config file
	to_get = [ PluginModuleConfig.from_class_name(class_name) for class_name in available_mods ] if config.plugins is None else config.plugins
	res = {}
	for mod in to_get:
		if mod.class_name in available_mods:
			# Don't silently overwrite available mappings
			if mod.name in res:
				log.fatal('duplicate_key', key=mod.name)
			res[mod.name] = available_mods[mod.class_name]
		else:
			log.fatal('missing_class', module=mod.name, class_name=mod.class_name)

	unbind_contextvars('plugin', 'file')
	return res

def load_path(path:str) -> dict:
	path = Path(path)
	config = None

	if not path.exists():
		log.fatal('not_found', file=str(path))

	try:
		if os.path.isfile(path): # Load directly if path is a file and not a dir
			files = [PluginFileConfig(None, path, None, None)]
			config = PluginConfig(files)
		elif os.path.isfile(path / "config.yaml"): # Check for a config.yaml in dir
			config = load_config_file(PluginConfig, path / 'config.yaml') # Let exceptions bubble up
			for file in config.files:
				file.file = path / file.file # Make path relative to script
		else:
			# Recreate a dummy PluginFileConfig without any of the specifics
			files = [ PluginFileConfig(None, file, None, None) for file in filter(lambda p: os.path.isfile(p) and p.suffix == '.py', map(lambda p: path / p, os.listdir(path))) ]
			config = PluginConfig(files)
	except UnicodeDecodeError as e:
		log.fatal('invalid_unicode', file=str(path), reason=e.reason, invalid_slice=e.object[e.start:e.end])
	except FileNotFoundError as e:
		log.fatal('not_found', file=str(path))
	except IsADirectoryError as e:
		log.fatal('is_directory', file=str(path))
	except PermissionError as e:
		log.fatal('permission_denied', file=str(path))
	except OSError as e:
		log.fatal('os_error', file=str(path), errno=e.errno)

	# Load each file and then merge into a single map
	res = {}
	for file_config in config.files:
		file_plugins = load_plugin(file_config)
		for (name, plugin) in file_plugins.items():
			if name in res:
				log.fatal('duplicate_definition', file=file_config.file, key=name)
			else:
				res[name] = plugin

	return res

def load_paths(paths:list[str]) -> dict:
	res = {}
	for path in paths:
		file_plugins = load_path(path)
		for (name, plugin) in file_plugins.items():
			if name in res:
				log.fatal('duplicate_definition', file=path, key=name)
			else:
				res[name] = plugin

	return res
