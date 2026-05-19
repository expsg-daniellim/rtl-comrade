"""Shared fixtures for harness test suite."""

import pytest

from rtl_comrade.testing import logging_handler  # noqa: F401
from rtl_comrade.config import (
    GraphConfig,
    GraphConfigNode,
    GraphConfigEdge,
    GraphConfigSrcPort,
    GraphConfigDstPort,
)


@pytest.fixture
def minimal_module_src():
    return "class Mod:\n    def run(self):\n        return None\n"


@pytest.fixture
def passthrough_module_src():
    return "class Mod:\n    def run(self, a):\n        return a\n"


@pytest.fixture
def tmp_plugin_dir(tmp_path):
    def _make(src, *, config=None):
        plugin_file = tmp_path / "plugin.py"
        plugin_file.write_text(src)
        if config is not None:
            config_file = tmp_path / "config.yaml"
            config_file.write_text(config)
        return tmp_path

    return _make


@pytest.fixture
def make_graph_config():
    def _make(nodes, edges, *, modules=(), contracts=()):
        node_objs = [
            GraphConfigNode(
                id=n["id"],
                module=n["module"],
                config=n.get("config", {}),
                contract=n.get("contract", ""),
                contract_config=n.get("contract_config", {}),
            )
            for n in nodes
        ]
        edge_objs = [
            GraphConfigEdge(
                src=GraphConfigSrcPort(
                    node=e["src"]["node"],
                    port=e["src"].get("port", "default"),
                ),
                dst=GraphConfigDstPort(
                    node=e["dst"]["node"],
                    port=e["dst"].get("port", 1),
                ),
            )
            for e in edges
        ]
        return GraphConfig(
            nodes=node_objs,
            edges=edge_objs,
            modules=list(modules),
            contracts=list(contracts),
        )

    return _make
