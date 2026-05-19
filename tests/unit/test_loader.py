"""Unit tests for loader.py — plugin discovery and loading."""

import textwrap
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from rtl_comrade.loader import (
    PluginModuleConfig,
    load_config_file,
    load_paths,
    load_plugin,
    load_path,
    PluginFileConfig,
    PluginConfig,
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
