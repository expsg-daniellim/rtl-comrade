"""Tests for modules/rtl_buddy/build.py — RunPreprocMod."""

import importlib.util
from pathlib import Path

from modules.rtl_buddy.schema import RootConfig, RootRtlField, TestResult, KeyedValue, ModelConfig
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_build",
    Path(__file__).parent.parent / "rtl_buddy" / "build.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RunPreprocMod = _mod.RunPreprocMod


def _make_tb():
    return TestbenchConfig(name="tb_top", filelist=["rtl/top.sv"])


def _make_test(name, **overrides):
    defaults = dict(
        name=name,
        desc=f"{name} test",
        model="sandbox",
        model_path="models.yaml",
        suite_dir=Path("/design/verif"),
        reglvl=None,
        pa=None,
        pd=None,
        uvm=None,
        preproc_path=None,
        postproc_path=None,
        sweep_path=None,
        tb=_make_tb(),
        timeout=None,
    )
    defaults.update(overrides)
    return TestConfig(**defaults)


def _make_model(key:str, name:str = "sandbox"):
    return KeyedValue(key, ModelConfig(name=name, filelist=["rtl/model.sv"]))


def _make_root_cfg():
    return RootConfig(platforms=[], rtl_builder_cfgs={}, cfg_rtl_reg=RootRtlField(path=""))


# ---------------------------------------------------------------------------
# RunPreprocMod
# ---------------------------------------------------------------------------


def test_run_preproc_no_script():
    test = _make_test("t1")  # preproc_path=None by default
    model = _make_model(test.key)
    root_cfg = _make_root_cfg()
    mod = RunPreprocMod()
    results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
    assert len(results) == 2
    assert results[0] == ("test", test)
    assert results[1] == ("model", model)


def test_run_preproc_mutations(tmp_path):
    script = tmp_path / "preproc.py"
    script.write_text(
        "test_cfg.set_plusarg('SEED', 42)\n"
        "test_cfg.set_plusdefine('DEBUG', 1)\n"
        "test_cfg.set_timeout(300)\n"
    )
    test = _make_test("t1", preproc_path=str(script))
    model = _make_model(test.key)
    root_cfg = _make_root_cfg()
    mod = RunPreprocMod()
    results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
    assert len(results) == 2
    port_t, emitted_test = results[0]
    port_m, emitted_model = results[1]
    assert port_t == "test"
    assert port_m == "model"
    assert emitted_test is test
    assert emitted_test.pa == {"SEED": 42}
    assert emitted_test.pd == {"DEBUG": 1}
    assert emitted_test.timeout == 300
    assert emitted_test.model == "sandbox"  # name string restored after exec
    assert emitted_model is model


def test_run_preproc_script_sees_resolved_model(tmp_path):
    script = tmp_path / "preproc.py"
    script.write_text(
        "test_cfg.set_plusdefine('MODEL', test_cfg.model.get_model_name())\n"
    )
    test = _make_test("t1", preproc_path=str(script))
    model = _make_model(test.key, name="sandbox")
    root_cfg = _make_root_cfg()
    mod = RunPreprocMod()
    results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
    assert len(results) == 2
    port_t, emitted_test = results[0]
    assert port_t == "test"
    assert emitted_test.pd == {"MODEL": "sandbox"}  # mutation from resolved model persists
    assert emitted_test.model == "sandbox"  # name string restored


def test_run_preproc_script_raises(tmp_path, logging_handler):
    script = tmp_path / "preproc.py"
    script.write_text("raise ValueError('boom')\n")
    test = _make_test("t1", preproc_path=str(script))
    model = _make_model(test.key)
    root_cfg = _make_root_cfg()
    mod = RunPreprocMod()
    results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
    assert len(results) == 1
    port, val = results[0]
    assert port == "fail"
    assert isinstance(val, TestResult)
    assert val.result == "FAIL"
    assert logging_handler.failure is True
    assert test.model == "sandbox"  # restored synchronously before the fail yield


def test_run_preproc_script_not_found(tmp_path, logging_handler):
    test = _make_test("t1", preproc_path=str(tmp_path / "nonexistent.py"))
    model = _make_model(test.key)
    root_cfg = _make_root_cfg()
    mod = RunPreprocMod()
    results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
    assert len(results) == 1
    port, val = results[0]
    assert port == "fail"
    assert isinstance(val, TestResult)
    assert val.result == "FAIL"
    assert logging_handler.failure is True
