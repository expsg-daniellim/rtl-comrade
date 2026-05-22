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
	load_paths,
	load_plugin,
	load_path,
	PluginFileConfig,
)
from rtl_comrade.config import GraphConfig


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
	cfg = load_config_file(GraphConfig, p)
	assert cfg is not None
	assert len(cfg.nodes) == 1


def test_load_config_file_not_found(logging_handler):
	with pytest.raises(SystemExit):
		load_config_file(GraphConfig, Path("/nonexistent/graph.yaml"))


def test_load_config_file_malformed_yaml(logging_handler, tmp_path):
	p = tmp_path / "bad.yaml"
	p.write_text("nodes: [\nunclosed bracket\n")
	with pytest.raises(SystemExit):
		load_config_file(GraphConfig, p)


def test_load_config_file_serde_mismatch(logging_handler, tmp_path):
	p = tmp_path / "bad.yaml"
	p.write_text("nodes: not_a_list\nedges: []\n")
	with pytest.raises(SystemExit):
		load_config_file(GraphConfig, p)


def test_load_config_file_permission_denied(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	with patch("builtins.open", side_effect=PermissionError("denied")):
		with pytest.raises(SystemExit):
			load_config_file(GraphConfig, p)


def test_load_config_file_unicode_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	exc = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
	with patch("builtins.open", side_effect=exc):
		with pytest.raises(SystemExit):
			load_config_file(GraphConfig, p)


def test_load_config_file_is_directory(logging_handler, tmp_path):
	with patch("builtins.open", side_effect=IsADirectoryError("is a directory")):
		with pytest.raises(SystemExit):
			load_config_file(GraphConfig, tmp_path / "graph.yaml")


def test_load_config_file_os_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	with patch("builtins.open", side_effect=OSError(5, "I/O error")):
		with pytest.raises(SystemExit):
			load_config_file(GraphConfig, p)


def test_load_config_file_reader_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	exc = ReaderError("test.yaml", 0, 0xFF, "utf-8", "special characters not allowed")
	with patch("rtl_comrade.loader.from_yaml", side_effect=exc):
		with pytest.raises(SystemExit):
			load_config_file(GraphConfig, p)


# --- load_plugin ---

_SIMPLE_PLUGIN = textwrap.dedent("""\
    class Foo:
        def run(self):
            return None

    class Bar:
        def run(self):
            return None
""")


def test_load_plugin_all_classes(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	result = load_plugin(config)
	assert "foo" in result
	assert "bar" in result


def test_load_plugin_explicit_list(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	plugins = [PluginModuleConfig(class_name="Foo", name="my_foo")]
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=plugins)
	result = load_plugin(config)
	assert "my_foo" in result
	assert "bar" not in result


def test_load_plugin_missing_class(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	plugins = [PluginModuleConfig(class_name="Missing", name="missing")]
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=plugins)
	with pytest.raises(SystemExit):
		load_plugin(config)


def test_load_plugin_duplicate_name(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	plugins = [
		PluginModuleConfig(class_name="Foo", name="same"),
		PluginModuleConfig(class_name="Bar", name="same"),
	]
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=plugins)
	with pytest.raises(SystemExit):
		load_plugin(config)


def test_load_plugin_not_a_file(logging_handler, tmp_path):
	# Pass a directory path — config.file.is_file() returns False → fatal.
	config = PluginFileConfig(name=None, file=tmp_path, type_=None, plugins=None)
	with pytest.raises(SystemExit):
		load_plugin(config)


def test_load_plugin_spec_none(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	with patch("rtl_comrade.loader.importlib.util.spec_from_file_location", return_value=None):
		with pytest.raises(SystemExit):
			load_plugin(config)


def test_load_plugin_spec_loader_none(logging_handler, tmp_path):
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
			load_plugin(config)


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
def test_load_plugin_exec_module_raises_fatal(logging_handler, tmp_path, exc):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	config = PluginFileConfig(name=None, file=plugin_file, type_=None, plugins=None)
	p1, p2 = _exec_raising_patches(exc)
	with p1, p2:
		with pytest.raises(SystemExit):
			load_plugin(config)


# --- load_path ---


def test_load_path_single_file(logging_handler, tmp_path):
	plugin_file = tmp_path / "mods.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	result = load_path(plugin_file)
	assert "foo" in result
	assert "bar" in result


def test_load_path_directory_no_config(logging_handler, tmp_path):
	plugin_file = tmp_path / "stuff.py"
	plugin_file.write_text(_SIMPLE_PLUGIN)
	result = load_path(tmp_path)
	assert "foo" in result or "bar" in result


def test_load_path_directory_with_config(logging_handler, tmp_path):
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
	result = load_path(tmp_path)
	assert "custom_foo" in result


def test_load_path_nonexistent(logging_handler):
	with pytest.raises(SystemExit):
		load_path(Path("/no/such/path"))


# --- load_paths ---


def test_load_paths_merges(logging_handler, tmp_path):
	dir_a = tmp_path / "a"
	dir_a.mkdir()
	(dir_a / "m1.py").write_text("class Alpha:\n    def run(self): return None\n")
	dir_b = tmp_path / "b"
	dir_b.mkdir()
	(dir_b / "m2.py").write_text("class Beta:\n    def run(self): return None\n")
	result = load_paths([dir_a, dir_b])
	assert "alpha" in result
	assert "beta" in result


def test_load_paths_duplicate_fatal(logging_handler, tmp_path):
	dir_a = tmp_path / "a"
	dir_a.mkdir()
	(dir_a / "m1.py").write_text("class Alpha:\n    def run(self): return None\n")
	dir_b = tmp_path / "b"
	dir_b.mkdir()
	(dir_b / "m2.py").write_text("class Alpha:\n    def run(self): return None\n")
	with pytest.raises(SystemExit):
		load_paths([dir_a, dir_b])


def test_load_path_duplicate_definition_in_dir_fatal(logging_handler, tmp_path):
	# Two files in the same dir both export a class with the same snake_case name.
	(tmp_path / "a.py").write_text("class Foo:\n    def run(self): return None\n")
	(tmp_path / "b.py").write_text("class Foo:\n    def run(self): return None\n")
	with pytest.raises(SystemExit):
		load_path(tmp_path)


def test_load_path_listdir_permission_error(logging_handler, tmp_path):
	# tmp_path has no config.yaml → else branch → os.listdir raises.
	with patch("os.listdir", side_effect=PermissionError("denied")):
		with pytest.raises(SystemExit):
			load_path(tmp_path)


def test_load_path_listdir_os_error(logging_handler, tmp_path):
	with patch("os.listdir", side_effect=OSError(5, "I/O error")):
		with pytest.raises(SystemExit):
			load_path(tmp_path)


def test_load_path_listdir_unicode_error(logging_handler, tmp_path):
	exc = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
	with patch("os.listdir", side_effect=exc):
		with pytest.raises(SystemExit):
			load_path(tmp_path)


def test_load_path_listdir_file_not_found(logging_handler, tmp_path):
	with patch("os.listdir", side_effect=FileNotFoundError("gone")):
		with pytest.raises(SystemExit):
			load_path(tmp_path)


def test_load_path_listdir_is_directory_error(logging_handler, tmp_path):
	with patch("os.listdir", side_effect=IsADirectoryError("not a dir")):
		with pytest.raises(SystemExit):
			load_path(tmp_path)


# --- cross-file import (dependency loading) ---


def test_load_path_package_cross_file_import(logging_handler, tmp_path):
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
	import sys as _sys
	result = load_path(pkg)
	assert "main" in result
	assert "helper" in result
	helpers_mod = _sys.modules["mypkg.helpers"]
	assert helpers_mod._load_count == 1, "helpers.py executed more than once"
	assert result["main"].dep is helpers_mod.Helper, "class identity split between importer and loader"
	assert str(tmp_path) in _sys.path


def test_load_path_plain_dir_cross_file_import(logging_handler, tmp_path):
	mods = tmp_path / "mods"
	mods.mkdir()
	(mods / "helpers.py").write_text("class Helper:\n    pass\n")
	(mods / "main.py").write_text(
		"from helpers import Helper\n"
		"class Main:\n"
		"    dep = Helper\n"
	)
	import sys as _sys
	result = load_path(mods)
	assert "main" in result
	assert str(mods) in _sys.path
