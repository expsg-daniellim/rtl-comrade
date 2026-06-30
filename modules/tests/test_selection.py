"""Tests for modules/rtl_buddy/setup.py selection/expansion modules."""

import importlib.util
from pathlib import Path

from modules.rtl_buddy.schema import SuiteConfig

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_setup",
    Path(__file__).parent.parent / "rtl_buddy" / "setup.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RouteListModeMod = _mod.RouteListModeMod


def _suite_cfg(tests=None):
    return SuiteConfig(path=Path("/fake/tests.yaml"), tests=tests or {})


# ---------------------------------------------------------------------------
# RouteListModeMod
# ---------------------------------------------------------------------------


def test_route_list_mode_list_true():
    cfg = _suite_cfg({"t1": None})
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg, list=True)
    assert port == "list"
    assert result is cfg


def test_route_list_mode_list_false():
    cfg = _suite_cfg({"t1": None})
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg, list=False)
    assert port == "run"
    assert result is cfg


def test_route_list_mode_default():
    cfg = _suite_cfg({"t1": None})
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg)
    assert port == "run"
    assert result is cfg


def test_route_list_mode_empty_suite():
    cfg = _suite_cfg()
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg, list=False)
    assert port == "run"
    assert result is cfg
