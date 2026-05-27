"""Unit tests for loader.py — plugin discovery and loading."""

import textwrap
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from yaml.reader import ReaderError

from rtl_comrade.loader import (
	PluginModuleConfig,
	load_config_file,
	load_plugin_config,
	load_plugin_configs,
	load_plugins,
	PluginFileConfig,
)
from rtl_comrade.config import GraphFileConfig


# --- PluginModuleConfig.from_class_name ---


def test_from_class_name_camel():
	r = PluginModuleConfig.from_class_name("FooBar")
	assert r.name == "foo_bar"


def test_from_class_name_acronym():
	r = PluginModuleConfig.from_class_name("ALUMod")
	assert r.name == "alu_mod"


def test_from_class_name_single():
	r = PluginModuleConfig.from_class_name("Simple")
	assert r.name == "simple"


# --- load_config_file ---


def test_load_config_file_valid(logging_handler, tmp_path):
	yaml_content = "nodes:\n- id: n1\n  module: m1\nedges: []\n"
	p = tmp_path / "graph.yaml"
	p.write_text(yaml_content)
	cfg = load_config_file(GraphFileConfig, p)
	assert cfg is not None
	assert len(cfg.nodes) == 1


def test_load_config_file_with_parent(logging_handler, tmp_path):
	subdir = tmp_path / "configs"
	subdir.mkdir()
	(subdir / "graph.yaml").write_text("nodes:\n- id: n1\n  module: m1\nedges: []\n")
	cfg = load_config_file(GraphFileConfig, Path("graph.yaml"), parent=subdir)
	assert cfg is not None
	assert len(cfg.nodes) == 1


def test_load_config_file_not_found(logging_handler):
	with pytest.raises(SystemExit):
		load_config_file(GraphFileConfig, Path("/nonexistent/graph.yaml"))


def test_load_config_file_malformed_yaml(logging_handler, tmp_path):
	p = tmp_path / "bad.yaml"
	p.write_text("nodes: [\nunclosed bracket\n")
	with pytest.raises(SystemExit):
		load_config_file(GraphFileConfig, p)


def test_load_config_file_serde_mismatch(logging_handler, tmp_path):
	p = tmp_path / "bad.yaml"
	p.write_text("nodes: not_a_list\nedges: []\n")
	with pytest.raises(SystemExit):
		load_config_file(GraphFileConfig, p)


def test_load_config_file_permission_denied(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	with patch("builtins.open", side_effect=PermissionError("denied")):
		with pytest.raises(SystemExit):
			load_config_file(GraphFileConfig, p)


def test_load_config_file_unicode_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	exc = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
	with patch("builtins.open", side_effect=exc):
		with pytest.raises(SystemExit):
			load_config_file(GraphFileConfig, p)


def test_load_config_file_is_directory(logging_handler, tmp_path):
	with patch("builtins.open", side_effect=IsADirectoryError("is a directory")):
		with pytest.raises(SystemExit):
			load_config_file(GraphFileConfig, tmp_path / "graph.yaml")


def test_load_config_file_os_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	with patch("builtins.open", side_effect=OSError(5, "I/O error")):
		with pytest.raises(SystemExit):
			load_config_file(GraphFileConfig, p)


def test_load_config_file_reader_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	exc = ReaderError("test.yaml", 0, 0xFF, "utf-8", "special characters not allowed")
	with patch("rtl_comrade.loader.from_yaml", side_effect=exc):
		with pytest.raises(SystemExit):
			load_config_file(GraphFileConfig, p)


# --- PluginFileConfig.load ---

_SIMPLE_PLUGIN = textwrap.dedent("""\
    class Foo:
        def run(self):
            return None

    class Bar:
        def run(self):
            return None
""")


def test_plugin_file_config_load_all_classes(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	result = config.load()
	assert "foo" in result
	assert "bar" in result


def test_plugin_file_config_load_explicit_list(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	plugins = [PluginModuleConfig(class_name="Foo", name="my_foo")]
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=plugins)
	result = config.load()
	assert "my_foo" in result
	assert "bar" not in result


def test_plugin_file_config_load_missing_class(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	plugins = [PluginModuleConfig(class_name="Missing", name="missing")]
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=plugins)
	with pytest.raises(SystemExit):
		config.load()


def test_plugin_file_config_load_duplicate_name(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	plugins = [
		PluginModuleConfig(class_name="Foo", name="same"),
		PluginModuleConfig(class_name="Bar", name="same"),
	]
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=plugins)
	with pytest.raises(SystemExit):
		config.load()


def test_plugin_file_config_load_not_a_file(logging_handler, tmp_path):
	# Pass a directory path — config.file.is_file() returns False → fatal.
	config = PluginFileConfig(name=None, file=tmp_path, type_=None, plugins=None)
	with pytest.raises(SystemExit):
		config.load()


def test_plugin_file_config_load_spec_none(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	with patch("rtl_comrade.loader.importlib.util.spec_from_file_location", return_value=None):
		with pytest.raises(SystemExit):
			config.load()


def test_plugin_file_config_load_spec_loader_none(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	mock_spec = MagicMock()
	mock_spec.loader = None
	with patch(
		"rtl_comrade.loader.importlib.util.spec_from_file_location",
		return_value=mock_spec,
	):
		with pytest.raises(SystemExit):
			config.load()


def _exec_raising_patches(exc):
	"""Return a pair of patches that make exec_module raise exc."""
	mock_loader = MagicMock()
	mock_loader.exec_module.side_effect = exc
	mock_spec = MagicMock()
	mock_spec.loader = mock_loader
	fake_module = types.ModuleType("test_plugin")
	return (
		patch(
			"rtl_comrade.loader.importlib.util.spec_from_file_location",
			return_value=mock_spec,
		),
		patch(
			"rtl_comrade.loader.importlib.util.module_from_spec",
			return_value=fake_module,
		),
	)


@pytest.mark.parametrize(
	"exc",
	[
		UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte"),
		FileNotFoundError("not found"),
		IsADirectoryError("is a directory"),
		PermissionError("permission denied"),
		OSError(5, "I/O error"),
		SyntaxError("bad syntax"),
		ValueError("value error"),
		TypeError("type error"),
		ModuleNotFoundError("no module"),
		ImportError("import error"),
		RuntimeError("generic exception"),
	],
	ids=[
		"unicode",
		"file_not_found",
		"is_directory",
		"permission",
		"os_error",
		"syntax",
		"value",
		"type",
		"module_not_found",
		"import",
		"generic",
	],
)
def test_plugin_file_config_load_exec_module_raises_fatal(logging_handler, tmp_path, exc):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	p1, p2 = _exec_raising_patches(exc)
	with p1, p2:
		with pytest.raises(SystemExit):
			config.load()


# --- load_plugins (single path) ---


def test_load_plugins_from_single_file(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	result = load_plugins(load_plugin_config(plugin_file))
	assert "foo" in result
	assert "bar" in result


def test_load_plugins_from_directory_no_config(logging_handler, tmp_path):
	plugin_file = tmp_path / "stuff.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	result = load_plugins(load_plugin_config(tmp_path))
	assert "foo" in result or "bar" in result


def test_load_plugins_from_directory_with_config(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config_yaml = textwrap.dedent("""\
        files:
        - file: mods.py
          name: null
          type_: null
          plugins:
          - class_name: Foo
            name: custom_foo
    """)
	(tmp_path / "config.yaml").write_text(config_yaml)
	result = load_plugins(load_plugin_config(tmp_path))
	assert "custom_foo" in result


def test_load_plugin_config_nonexistent_path(logging_handler):
	with pytest.raises(SystemExit):
		load_plugins(load_plugin_config(Path("/no/such/path")))


# --- load_plugin_configs / load_plugins (multiple paths) ---


def test_load_plugins_merges_from_multiple_paths(logging_handler, tmp_path):
	dir_a = tmp_path / "a"
	dir_a.mkdir()
	(dir_a / "m1.py").write_text("class Alpha:\n    def run(self): return None\n")
	dir_b = tmp_path / "b"
	dir_b.mkdir()
	(dir_b / "m2.py").write_text("class Beta:\n    def run(self): return None\n")
	result = load_plugins(load_plugin_configs([str(dir_a), str(dir_b)]))
	assert "alpha" in result
	assert "beta" in result


def test_load_plugins_duplicate_from_multiple_paths_fatal(logging_handler, tmp_path):
	dir_a = tmp_path / "a"
	dir_a.mkdir()
	(dir_a / "m1.py").write_text("class Alpha:\n    def run(self): return None\n")
	dir_b = tmp_path / "b"
	dir_b.mkdir()
	(dir_b / "m2.py").write_text("class Alpha:\n    def run(self): return None\n")
	with pytest.raises(SystemExit):
		load_plugins(load_plugin_configs([str(dir_a), str(dir_b)]))


def test_load_plugins_duplicate_definition_in_dir_fatal(logging_handler, tmp_path):
	# Two files in the same dir both export a class with the same snake_case name.
	(tmp_path / "a.py").write_text("class Foo:\n    def run(self): return None\n")
	(tmp_path / "b.py").write_text("class Foo:\n    def run(self): return None\n")
	with pytest.raises(SystemExit):
		load_plugins(load_plugin_config(tmp_path))


def test_load_plugin_config_listdir_permission_error(logging_handler, tmp_path):
	# tmp_path has no config.yaml → else branch → os.listdir raises.
	with patch("os.listdir", side_effect=PermissionError("denied")):
		with pytest.raises(SystemExit):
			load_plugin_config(tmp_path)


def test_load_plugin_config_listdir_os_error(logging_handler, tmp_path):
	with patch("os.listdir", side_effect=OSError(5, "I/O error")):
		with pytest.raises(SystemExit):
			load_plugin_config(tmp_path)


def test_load_plugin_config_listdir_unicode_error(logging_handler, tmp_path):
	exc = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
	with patch("os.listdir", side_effect=exc):
		with pytest.raises(SystemExit):
			load_plugin_config(tmp_path)


def test_load_plugin_config_listdir_file_not_found(logging_handler, tmp_path):
	with patch("os.listdir", side_effect=FileNotFoundError("gone")):
		with pytest.raises(SystemExit):
			load_plugin_config(tmp_path)


def test_load_plugin_config_listdir_is_directory_error(logging_handler, tmp_path):
	with patch("os.listdir", side_effect=IsADirectoryError("not a dir")):
		with pytest.raises(SystemExit):
			load_plugin_config(tmp_path)


# --- cross-file import (dependency loading) ---


def test_load_plugins_package_cross_file_import(logging_handler, tmp_path):
	pkg = tmp_path / "mypkg"
	pkg.mkdir()
	(pkg / "__init__.py").write_text("")
	(pkg / "helpers.py").write_text(
		"_load_count = 0\n"
		"_load_count += 1\n"
		"class Helper:\n"
		"    pass\n"
	)
	(pkg / "main.py").write_text(
		"from mypkg.helpers import Helper\n"
		"class Main:\n"
		"    dep = Helper\n"
	)
	import sys as _sys  # pylint: disable=import-outside-toplevel
	result = load_plugins(load_plugin_config(pkg))
	assert "main" in result
	assert "helper" in result
	helpers_mod = _sys.modules["mypkg.helpers"]
	assert helpers_mod._load_count == 1, "helpers.py executed more than once"  # pylint: disable=protected-access
	assert result["main"].dep is helpers_mod.Helper, "class identity split between importer and loader"
	assert str(tmp_path) in _sys.path


def test_load_plugins_plain_dir_cross_file_import(logging_handler, tmp_path):
	mods = tmp_path / "mods"
	mods.mkdir()
	(mods / "helpers.py").write_text("class Helper:\n    pass\n")
	(mods / "main.py").write_text(
		"from helpers import Helper\n"
		"class Main:\n"
		"    dep = Helper\n"
	)
	import sys as _sys  # pylint: disable=import-outside-toplevel
	result = load_plugins(load_plugin_config(mods))
	assert "main" in result
	assert str(mods) in _sys.path


# --- module-cache branches in PluginFileConfig.load ---


def test_plugin_file_config_load_canonical_relative_to_error_falls_back_to_fresh_load(logging_handler, tmp_path):
	# Package dir exists (__init__.py present) but relative_to raises ValueError →
	# canonical_name = None → fresh load via else branch.
	pkg = tmp_path / "pkg"
	pkg.mkdir()
	(pkg / "__init__.py").write_text("")
	plugin_file = pkg / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name="pkg_mods_relative_err", file=plugin_file, type_=None, plugins=None)
	with patch.object(Path, "relative_to", side_effect=ValueError("no common prefix")):
		result = config.load()
	assert "foo" in result


def test_plugin_file_config_load_reuses_cached_module_by_plugin_name(logging_handler, tmp_path):
	# No __init__.py → canonical_name = None; plugin_name already in sys.modules → reuse.
	import sys as _sys  # pylint: disable=import-outside-toplevel
	plugin_file = tmp_path / "cached.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	plugin_name = "rtl_comrade_test_cached_reuse"
	fake_mod = types.ModuleType(plugin_name)

	class Baz:
		def run(self): return None  # pylint: disable=multiple-statements

	fake_mod.Baz = Baz
	_sys.modules[plugin_name] = fake_mod
	try:
		plugins = [PluginModuleConfig(class_name="Baz", name="baz")]
		config = PluginFileConfig(name=plugin_name, file=plugin_file, type_=None, plugins=plugins)
		result = config.load()
		assert result["baz"] is Baz
	finally:
		_sys.modules.pop(plugin_name, None)


# --- load_plugin_config ---


def test_load_plugin_config_single_file(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	result = load_plugin_config(plugin_file)
	assert len(result) == 1
	assert result[0].file == plugin_file


def test_load_plugin_config_directory_no_config(logging_handler, tmp_path):
	(tmp_path / "a.py").write_text(_SIMPLE_PLUGIN)
	(tmp_path / "b.py").write_text(_SIMPLE_PLUGIN)
	result = load_plugin_config(tmp_path)
	files = [r.file for r in result]
	assert tmp_path / "a.py" in files
	assert tmp_path / "b.py" in files


def test_load_plugin_config_directory_with_config(logging_handler, tmp_path):
	(tmp_path / "mods.py").write_text(_SIMPLE_PLUGIN)
	config_yaml = "files:\n- file: mods.py\n  name: null\n  type_: null\n  plugins: null\n"
	(tmp_path / "config.yaml").write_text(config_yaml)
	result = load_plugin_config(tmp_path)
	assert len(result) == 1
	assert result[0].file == tmp_path / "mods.py"


def test_load_plugin_config_deduplicates_duplicate_files(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config_yaml = (
		"files:\n"
		"- file: mods.py\n  name: null\n  type_: null\n  plugins: null\n"
		"- file: mods.py\n  name: null\n  type_: null\n  plugins: null\n"
	)
	(tmp_path / "config.yaml").write_text(config_yaml)
	result = load_plugin_config(tmp_path)
	assert len(result) == 1


def test_load_plugin_config_nonexistent_fatal(logging_handler):
	with pytest.raises(SystemExit):
		load_plugin_config(Path("/no/such/path"))


def test_load_plugin_config_with_relative_path_single_file(logging_handler, tmp_path):
	subdir = tmp_path / "plugins"
	subdir.mkdir()
	(subdir / "mods.py").write_text(_SIMPLE_PLUGIN)
	result = load_plugin_config(Path("plugins/mods.py"), relative_path=tmp_path)
	assert len(result) == 1
	assert result[0].file == subdir / "mods.py"


def test_load_plugin_config_with_relative_path_directory(logging_handler, tmp_path):
	subdir = tmp_path / "plugins"
	subdir.mkdir()
	(subdir / "mods.py").write_text(_SIMPLE_PLUGIN)
	result = load_plugin_config(Path("plugins"), relative_path=tmp_path)
	files = [r.file for r in result]
	assert subdir / "mods.py" in files


def test_load_plugin_config_does_not_load(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	with patch("rtl_comrade.loader.importlib.util.spec_from_file_location") as mock_spec:
		load_plugin_config(plugin_file)
		mock_spec.assert_not_called()


# --- load_plugin_configs ---


def test_load_plugin_configs_flat_concatenation(logging_handler, tmp_path):
	dir_a = tmp_path / "a"
	dir_a.mkdir()
	(dir_a / "m1.py").write_text("class Alpha:\n    pass\n")
	dir_b = tmp_path / "b"
	dir_b.mkdir()
	(dir_b / "m2.py").write_text("class Beta:\n    pass\n")
	result = load_plugin_configs([str(dir_a), str(dir_b)])
	files = [r.file for r in result]
	assert dir_a / "m1.py" in files
	assert dir_b / "m2.py" in files


def test_load_plugin_configs_deduplicates_duplicate_path_strings(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	result = load_plugin_configs([str(plugin_file), str(plugin_file)])
	assert len(result) == 1


def test_load_plugin_configs_empty(logging_handler):
	result = load_plugin_configs([])
	assert result == []


def test_load_plugin_configs_with_relative_path(logging_handler, tmp_path):
	subdir = tmp_path / "plugins"
	subdir.mkdir()
	(subdir / "mods.py").write_text(_SIMPLE_PLUGIN)
	result = load_plugin_configs(["plugins"], relative_path=tmp_path)
	files = [r.file for r in result]
	assert subdir / "mods.py" in files


# --- load_plugins ---


def test_load_plugins_happy_path(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	configs = [PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)]
	result = load_plugins(configs)
	assert "foo" in result
	assert "bar" in result


def test_load_plugins_merges_multiple_files(logging_handler, tmp_path):
	(tmp_path / "a.py").write_text("class Alpha:\n    def run(self): return None\n")
	(tmp_path / "b.py").write_text("class Beta:\n    def run(self): return None\n")
	configs = [
		PluginFileConfig(name=None, file=tmp_path / "a.py", type_=None, plugins=None),
		PluginFileConfig(name=None, file=tmp_path / "b.py", type_=None, plugins=None),
	]
	result = load_plugins(configs)
	assert "alpha" in result
	assert "beta" in result


def test_load_plugins_duplicate_name_fatal(logging_handler, tmp_path):
	(tmp_path / "a.py").write_text("class Foo:\n    def run(self): return None\n")
	(tmp_path / "b.py").write_text("class Foo:\n    def run(self): return None\n")
	configs = [
		PluginFileConfig(name=None, file=tmp_path / "a.py", type_=None, plugins=None),
		PluginFileConfig(name=None, file=tmp_path / "b.py", type_=None, plugins=None),
	]
	with pytest.raises(SystemExit):
		load_plugins(configs)


def test_load_plugins_empty(logging_handler):
	result = load_plugins([])
	assert result == {}


# --- PluginFileConfig.load ---


def test_plugin_file_config_load_imports_classes(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	result = config.load()
	assert "foo" in result
	assert "bar" in result


def test_plugin_file_config_load_injects_sys_path(logging_handler, tmp_path):
	import sys as _sys  # pylint: disable=import-outside-toplevel
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	config.load()
	assert str(tmp_path) in _sys.path
