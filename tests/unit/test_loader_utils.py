"""Unit tests for loader_utils.py — YAML config-file loading.

import_plugin_file is exercised via PluginFileConfig.load in test_loader_plugin.py.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from yaml.reader import ReaderError

from rtl_comrade.loader_utils import load_config_file
from rtl_comrade.config import GraphFileConfig


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
	with pytest.raises(typer.Exit):
		load_config_file(GraphFileConfig, Path("/nonexistent/graph.yaml"))


def test_load_config_file_malformed_yaml(logging_handler, tmp_path):
	p = tmp_path / "bad.yaml"
	p.write_text("nodes: [\nunclosed bracket\n")
	with pytest.raises(typer.Exit):
		load_config_file(GraphFileConfig, p)


def test_load_config_file_serde_mismatch(logging_handler, tmp_path):
	p = tmp_path / "bad.yaml"
	p.write_text("nodes: not_a_list\nedges: []\n")
	with pytest.raises(typer.Exit):
		load_config_file(GraphFileConfig, p)


def test_load_config_file_permission_denied(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	with patch("builtins.open", side_effect=PermissionError("denied")):
		with pytest.raises(typer.Exit):
			load_config_file(GraphFileConfig, p)


def test_load_config_file_unicode_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	exc = UnicodeDecodeError("utf-8", b"\x80", 0, 1, "invalid start byte")
	with patch("builtins.open", side_effect=exc):
		with pytest.raises(typer.Exit):
			load_config_file(GraphFileConfig, p)


def test_load_config_file_is_directory(logging_handler, tmp_path):
	with patch("builtins.open", side_effect=IsADirectoryError("is a directory")):
		with pytest.raises(typer.Exit):
			load_config_file(GraphFileConfig, tmp_path / "graph.yaml")


def test_load_config_file_os_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	with patch("builtins.open", side_effect=OSError(5, "I/O error")):
		with pytest.raises(typer.Exit):
			load_config_file(GraphFileConfig, p)


def test_load_config_file_reader_error(logging_handler, tmp_path):
	p = tmp_path / "graph.yaml"
	p.write_text("nodes: []\nedges: []\n")
	exc = ReaderError("test.yaml", 0, 0xFF, "utf-8", "special characters not allowed")
	with patch("rtl_comrade.loader_utils.from_yaml", side_effect=exc):
		with pytest.raises(typer.Exit):
			load_config_file(GraphFileConfig, p)
