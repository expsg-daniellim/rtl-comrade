"""Unit tests for app.py — App CLI, config discovery, and error handling."""

import logging
import sys
from unittest.mock import patch

import pytest
import structlog
from typer.testing import CliRunner

from rtl_comrade.app import (
    DEFAULT_RTL_COMRADE_CONFIG_NAME,
    App,
    CommandConfig,
    RtlComradeConfig,
    search_for_config,
)

MINIMAL_CONFIG_YAML = "commands:\n  run:\n    path: graphs/test.yaml\n"
MINIMAL_CONFIG = RtlComradeConfig(commands={"run": CommandConfig(path="graphs/test.yaml")})

runner = CliRunner()


@pytest.fixture(autouse=True)
def reset_logging():
    yield
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)
    structlog.reset_defaults()


def _make_app(argv=None, config=None):
    with patch("rtl_comrade.app.search_for_config", return_value=config or MINIMAL_CONFIG), \
         patch.object(sys, "argv", argv or ["rtl-comrade"]):
        return App()


# ---------------------------------------------------------------------------
# search_for_config
# ---------------------------------------------------------------------------


def test_search_finds_config_in_given_dir(tmp_path):
    (tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
    result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
    assert result is not None
    assert result.commands["run"].path == "graphs/test.yaml"


def test_search_ascends_to_parent_dir(tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    (tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
    result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, child)
    assert result is not None
    assert "run" in result.commands


def test_search_stops_at_git_root_when_no_config(tmp_path):
    (tmp_path / ".git").mkdir()
    child = tmp_path / "child"
    child.mkdir()
    result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, child)
    assert result is None


def test_search_finds_config_at_git_root(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(MINIMAL_CONFIG_YAML)
    result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
    assert result is not None


def test_search_with_file_path_matching_name(tmp_path):
    f = tmp_path / "custom.yaml"
    f.write_text(MINIMAL_CONFIG_YAML)
    result = search_for_config("custom.yaml", f)
    assert result is not None


def test_search_with_file_path_not_matching_name(tmp_path):
    f = tmp_path / "other.yaml"
    f.write_text(MINIMAL_CONFIG_YAML)
    result = search_for_config("custom.yaml", f)
    assert result is None


def test_search_custom_name_does_not_match_default(tmp_path):
    (tmp_path / "custom.yaml").write_text(MINIMAL_CONFIG_YAML)
    result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
    assert result is None


def test_search_config_help_field_parsed(tmp_path):
    yaml = "commands:\n  run:\n    path: g.yaml\n    help: 'Run the ALU graph'\n"
    (tmp_path / DEFAULT_RTL_COMRADE_CONFIG_NAME).write_text(yaml)
    result = search_for_config(DEFAULT_RTL_COMRADE_CONFIG_NAME, tmp_path)
    assert result is not None
    assert result.commands["run"].help == "Run the ALU graph"


# ---------------------------------------------------------------------------
# App — startup
# ---------------------------------------------------------------------------


def test_app_config_not_found_exits():
    with patch("rtl_comrade.app.search_for_config", return_value=None), \
         patch.object(sys, "argv", ["rtl-comrade"]):
        with pytest.raises(SystemExit):
            App()


def test_app_logging_level_info_by_default():
    _make_app()
    assert logging.getLogger().level == logging.INFO


def test_app_logging_level_debug():
    _make_app(argv=["rtl-comrade", "--level", "debug"])
    assert logging.getLogger().level == logging.DEBUG


def test_app_logging_level_warning():
    _make_app(argv=["rtl-comrade", "--level", "warning"])
    assert logging.getLogger().level == logging.WARNING


def test_app_custom_config_file_loaded(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    (tmp_path / "custom.yaml").write_text(
        "commands:\n  mycmd:\n    path: my_graph.yaml\n"
    )
    monkeypatch.chdir(tmp_path)
    with patch.object(sys, "argv", ["rtl-comrade", "--config-file", "custom.yaml"]):
        app = App()
    with patch("rtl_comrade.app.Graph.from_file") as mock_from_file, \
         patch("rtl_comrade.app.asyncio.run"):
        runner.invoke(app.app, ["mycmd"])
    mock_from_file.assert_called_once_with("my_graph.yaml")


# ---------------------------------------------------------------------------
# App — subcommand dispatch and exit codes
# ---------------------------------------------------------------------------


def test_app_help_exits_0():
    app = _make_app()
    result = runner.invoke(app.app, ["--help"])
    assert result.exit_code == 0


def test_app_subcommand_exits_0_on_success():
    app = _make_app()
    with patch("rtl_comrade.app.Graph.from_file"), \
         patch("rtl_comrade.app.asyncio.run"):
        result = runner.invoke(app.app, ["run"])
    assert result.exit_code == 0


def test_app_subcommand_exits_1_on_graph_failure():
    app = _make_app()
    with patch("rtl_comrade.app.Graph.from_file"), \
         patch("rtl_comrade.app.asyncio.run"):
        app.handler.failure = True
        result = runner.invoke(app.app, ["run"])
    assert result.exit_code == 1


def test_app_subcommand_calls_graph_from_file():
    app = _make_app()
    with patch("rtl_comrade.app.Graph.from_file") as mock_from_file, \
         patch("rtl_comrade.app.asyncio.run"):
        runner.invoke(app.app, ["run"])
    mock_from_file.assert_called_once_with("graphs/test.yaml")


def test_app_unknown_subcommand_exits_nonzero():
    app = _make_app()
    result = runner.invoke(app.app, ["nonexistent"])
    assert result.exit_code != 0
