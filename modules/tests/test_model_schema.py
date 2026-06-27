"""Tests for modules/rtl_buddy/schema/model.py — spec 01c acceptance criteria."""

import dataclasses
import pytest

from modules.rtl_buddy.schema.model import ModelConfig


# ---------------------------------------------------------------------------
# Field parity
# ---------------------------------------------------------------------------


def test_field_parity():
    m = ModelConfig(name="test_module", filelist=["rtl/top.sv", "rtl/sub.sv"])
    assert m.name == "test_module"
    assert m.filelist == ["rtl/top.sv", "rtl/sub.sv"]
    assert m.path is None


def test_field_parity_with_path():
    m = ModelConfig(name="test_module", filelist=["rtl/top.sv"], path="/abs/models.yaml")
    assert m.name == "test_module"
    assert m.filelist == ["rtl/top.sv"]
    assert m.path == "/abs/models.yaml"


# ---------------------------------------------------------------------------
# Frozen
# ---------------------------------------------------------------------------


def test_frozen_rejects_assignment():
    m = ModelConfig(name="test_module", filelist=["a.sv"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.path = "/new/path"


def test_frozen_rejects_name_assignment():
    m = ModelConfig(name="test_module", filelist=["a.sv"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.name = "other"


# ---------------------------------------------------------------------------
# get_model_name returns self.name (bug fix vs rtl_buddy's self.model_name)
# ---------------------------------------------------------------------------


def test_get_model_name_returns_name():
    m = ModelConfig(name="sandbox", filelist=[])
    assert m.get_model_name() == "sandbox"
    assert m.get_model_name() == m.name


# ---------------------------------------------------------------------------
# get_filelist / get_model_path
# ---------------------------------------------------------------------------


def test_get_filelist():
    fl = ["rtl/top.sv", "rtl/pkg.sv"]
    m = ModelConfig(name="x", filelist=fl)
    assert m.get_filelist() == fl
    assert m.get_filelist() is m.filelist


def test_get_model_path_none():
    m = ModelConfig(name="x", filelist=[])
    assert m.get_model_path() is None


def test_get_model_path_set():
    m = ModelConfig(name="x", filelist=[], path="/design/models.yaml")
    assert m.get_model_path() == "/design/models.yaml"
    assert m.get_model_path() is m.path
