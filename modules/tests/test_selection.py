"""Tests for modules/rtl_buddy/setup.py selection/expansion modules."""

import importlib.util
import os
from pathlib import Path

import pytest
import typer
from serde.yaml import from_yaml

from modules.rtl_buddy.schema import SuiteConfig, KeyedValue, ModelConfig, RootConfig, RootRtlField
from modules.rtl_buddy.schema.suite import TestbenchConfig, TestConfig

_spec = importlib.util.spec_from_file_location(
	"modules_rtl_buddy_setup",
	Path(__file__).parent.parent / "rtl_buddy" / "setup.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RouteListModeMod = _mod.RouteListModeMod
ListTestNamesMod = _mod.ListTestNamesMod
SelectTestsMod = _mod.SelectTestsMod
FilterRegLvlMod = _mod.FilterRegLvlMod
LoadModelMod = _mod.LoadModelMod
ModelConfigFile = _mod.ModelConfigFile
ExpandSweepMod = _mod.ExpandSweepMod

_MODELS_FIXTURE = Path(__file__).parent / "fixtures" / "design" / "sandbox" / "models.yaml"


def _suite_cfg(tests=None):
	return SuiteConfig(path=Path("/fake/tests.yaml"), tests=tests or {})


# ---------------------------------------------------------------------------
# RouteListModeMod
# ---------------------------------------------------------------------------


def test_route_list_mode_list_true():
	cfg = _suite_cfg({"t1": None})
	mod = RouteListModeMod()
	port, result = mod.run(suite_cfg=cfg, list_=True)
	assert port == "list"
	assert result is cfg


def test_route_list_mode_list_false():
	cfg = _suite_cfg({"t1": None})
	mod = RouteListModeMod()
	port, result = mod.run(suite_cfg=cfg, list_=False)
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
	port, result = mod.run(suite_cfg=cfg, list_=False)
	assert port == "run"
	assert result is cfg


# ---------------------------------------------------------------------------
# ListTestNamesMod
# ---------------------------------------------------------------------------


def test_list_test_names_three_tests(capsys):
	cfg = _suite_cfg({"alpha": None, "beta": None, "gamma": None})
	mod = ListTestNamesMod()
	result = mod.run(suite_cfg=cfg)
	assert result is None
	assert capsys.readouterr().out == "alpha  beta  gamma\n"


def test_list_test_names_declaration_order(capsys):
	cfg = _suite_cfg({"zebra": None, "alpha": None})
	mod = ListTestNamesMod()
	mod.run(suite_cfg=cfg)
	assert capsys.readouterr().out == "zebra  alpha\n"


def test_list_test_names_single(capsys):
	cfg = _suite_cfg({"only": None})
	mod = ListTestNamesMod()
	mod.run(suite_cfg=cfg)
	assert capsys.readouterr().out == "only\n"


def test_list_test_names_empty(capsys):
	cfg = _suite_cfg()
	mod = ListTestNamesMod()
	mod.run(suite_cfg=cfg)
	assert capsys.readouterr().out == "\n"


# ---------------------------------------------------------------------------
# SelectTestsMod helpers
# ---------------------------------------------------------------------------


def _make_tb(**overrides):
	defaults = {"name": "tb_top", "filelist": ["rtl/top.sv"]}
	defaults.update(overrides)
	return TestbenchConfig(**defaults)


def _make_test(name, **overrides):
	defaults = {
		"name": name,
		"desc": f"{name} test",
		"model": "sandbox",
		"model_path": "models.yaml",
		"suite_dir": Path("/design/verif"),
		"reglvl": None,
		"pa": None,
		"pd": None,
		"uvm": None,
		"preproc_path": None,
		"postproc_path": None,
		"sweep_path": None,
		"tb": _make_tb(),
		"timeout": None,
	}
	defaults.update(overrides)
	return TestConfig(**defaults)


def _suite3():
	t1 = _make_test("foo")
	t2 = _make_test("bar")
	t3 = _make_test("baz")
	return SuiteConfig(path=Path("/fake/tests.yaml"), tests={"foo": t1, "bar": t2, "baz": t3})


def _empty_suite():
	return SuiteConfig(path=Path("/fake/tests.yaml"), tests={})


# ---------------------------------------------------------------------------
# SelectTestsMod
# ---------------------------------------------------------------------------


def test_select_tests_all_three():
	suite = _suite3()
	mod = SelectTestsMod()
	results = list(mod.run(suite_cfg=suite, test_name=""))
	assert len(results) == 3
	assert all(port == "test" for port, _ in results)
	tests = [t for _, t in results]
	assert [t.get_name() for t in tests] == ["foo", "bar", "baz"]
	assert all(t.key == t.get_name() for t in tests)


def test_select_tests_by_name():
	suite = _suite3()
	mod = SelectTestsMod()
	results = list(mod.run(suite_cfg=suite, test_name="foo"))
	assert len(results) == 1
	port, t = results[0]
	assert port == "test"
	assert t.get_name() == "foo"
	assert t is suite.tests["foo"]


def test_select_tests_nonexistent_fatal(logging_handler):
	suite = _suite3()
	mod = SelectTestsMod()
	with pytest.raises(typer.Exit):
		list(mod.run(suite_cfg=suite, test_name="nonexistent"))


def test_select_tests_empty_suite():
	suite = _empty_suite()
	mod = SelectTestsMod()
	results = list(mod.run(suite_cfg=suite, test_name=""))
	assert len(results) == 0


# ---------------------------------------------------------------------------
# FilterRegLvlMod helpers
# ---------------------------------------------------------------------------


class FakeBuilderCfg:
	def __init__(self, name):
		self.name = name

	def get_name(self):
		return self.name


# ---------------------------------------------------------------------------
# FilterRegLvlMod
# ---------------------------------------------------------------------------


def test_filter_reglvl_both_bounds_none():
	test = _make_test("foo", reglvl=3)
	builder_cfg = FakeBuilderCfg("b")
	mod = FilterRegLvlMod()
	port, value = mod.run(test=test, builder_cfg=builder_cfg)
	assert port == "test"
	assert value is test


def test_filter_reglvl_inside_window():
	test = _make_test("foo", reglvl=3)
	builder_cfg = FakeBuilderCfg("b")
	mod = FilterRegLvlMod()
	port, value = mod.run(test=test, builder_cfg=builder_cfg, reg_level=5, start_level=1)
	assert port == "test"
	assert value is test


def test_filter_reglvl_at_upper_boundary():
	test = _make_test("foo", reglvl=5)
	builder_cfg = FakeBuilderCfg("b")
	mod = FilterRegLvlMod()
	port, value = mod.run(test=test, builder_cfg=builder_cfg, reg_level=5, start_level=1)
	assert port == "test"
	assert value is test


def test_filter_reglvl_at_lower_boundary():
	test = _make_test("foo", reglvl=1)
	builder_cfg = FakeBuilderCfg("b")
	mod = FilterRegLvlMod()
	port, value = mod.run(test=test, builder_cfg=builder_cfg, reg_level=5, start_level=1)
	assert port == "test"
	assert value is test


def test_filter_reglvl_above_upper_bound(logging_handler):
	test = _make_test("foo", reglvl=6)
	builder_cfg = FakeBuilderCfg("b")
	mod = FilterRegLvlMod()
	result = mod.run(test=test, builder_cfg=builder_cfg, reg_level=5)
	assert result is None
	assert logging_handler.failure is False


def test_filter_reglvl_below_lower_bound(logging_handler):
	test = _make_test("foo", reglvl=0)
	builder_cfg = FakeBuilderCfg("b")
	mod = FilterRegLvlMod()
	result = mod.run(test=test, builder_cfg=builder_cfg, start_level=1)
	assert result is None
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# LoadModelMod helpers
# ---------------------------------------------------------------------------


def _make_model_test(name="alu", model="test_module", model_path="models.yaml", suite_dir=None, **overrides):
	return _make_test(name, model=model, model_path=model_path, suite_dir=suite_dir or _MODELS_FIXTURE.parent, **overrides)


# ---------------------------------------------------------------------------
# LoadModelMod
# ---------------------------------------------------------------------------


def test_load_model_happy_path(logging_handler):
	test = _make_model_test()
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 2
	port0, val0 = results[0]
	port1, val1 = results[1]
	assert port0 == "test"
	assert val0 is test
	assert test.model == "test_module"  # name string unchanged — not overwritten with ModelConfig
	assert port1 == "model"
	assert isinstance(val1, KeyedValue)
	assert val1.key == test.key
	assert val1.value.name == "test_module"
	assert val1.value.filelist == ["-F test_modules.f"]
	assert val1.value.path == str(_MODELS_FIXTURE)
	assert logging_handler.failure is False


def test_load_model_raw_shape_no_path():
	with open(_MODELS_FIXTURE, encoding="utf-8") as f:
		file_obj = from_yaml(ModelConfigFile, f.read())
	for item in file_obj.models:
		assert hasattr(item, 'name')
		assert hasattr(item, 'filelist')
		assert not hasattr(item, 'path')
	# emitted ModelConfig.path is set at construction from resolved, not from YAML
	test = _make_model_test()
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	_, val = results[1]
	assert val.value.path == str(_MODELS_FIXTURE)


def test_load_model_not_in_file(logging_handler):
	test = _make_model_test(model="nonexistent_model")
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_load_model_file_not_found(logging_handler):
	test = _make_model_test(model_path="nonexistent_models.yaml")
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_load_model_parse_error(tmp_path, logging_handler):
	bad = tmp_path / "models.yaml"
	bad.write_text("rtl-buddy-filetype: bad_type\nmodels: []\n")
	test = _make_model_test(model_path="models.yaml", suite_dir=tmp_path)
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_load_model_empty_models_list(tmp_path, logging_handler):
	empty = tmp_path / "models.yaml"
	empty.write_text("rtl-buddy-filetype: model_config\nmodels: []\n")
	test = _make_model_test(model_path="models.yaml", suite_dir=tmp_path)
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_load_model_is_directory(tmp_path, logging_handler):
	(tmp_path / "models.yaml").mkdir()
	test = _make_model_test(model_path="models.yaml", suite_dir=tmp_path)
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file-mode enforcement, so chmod 0o000 grants no denial")
def test_load_model_permission_denied(tmp_path, logging_handler):
	bad = tmp_path / "models.yaml"
	bad.write_text("rtl-buddy-filetype: model_config\nmodels: []\n")
	bad.chmod(0o000)
	test = _make_model_test(model_path="models.yaml", suite_dir=tmp_path)
	mod = LoadModelMod()
	try:
		results = list(mod.run(test=test))
	finally:
		bad.chmod(0o644)
	assert len(results) == 0
	assert logging_handler.failure is True


def test_load_model_invalid_unicode(tmp_path, logging_handler):
	bad = tmp_path / "models.yaml"
	bad.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
	test = _make_model_test(model_path="models.yaml", suite_dir=tmp_path)
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_load_model_os_error(tmp_path, logging_handler):
	test = _make_model_test(model_path="x" * 5000 + ".yaml", suite_dir=tmp_path)
	mod = LoadModelMod()
	results = list(mod.run(test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# ExpandSweepMod helpers
# ---------------------------------------------------------------------------


def _make_sweep_root_cfg():
	return RootConfig(platforms=[], rtl_builder_cfgs={}, cfg_rtl_reg=RootRtlField(path=""))


def _make_sweep_model(key:str, name:str = "sandbox"):
	return KeyedValue(key, ModelConfig(name=name, filelist=["rtl/model.sv"]))


# ---------------------------------------------------------------------------
# ExpandSweepMod
# ---------------------------------------------------------------------------


def test_expand_sweep_no_sweep():
	test = _make_test("t1")  # sweep_path=None by default
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 2
	assert results[0] == ("test", test)
	assert results[1] == ("model", model)
	assert test.key == "t1"  # unchanged


def test_expand_sweep_four_variants(tmp_path):
	script = tmp_path / "sweep.py"
	script.write_text(
		"import dataclasses\n"
		"for _ in range(4):\n"
		"    out_test_cfgs.append(dataclasses.replace(test_cfg))\n"
	)
	test = _make_test("t1", sweep_path=str(script))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 8
	for i in range(4):
		port_t, variant = results[i * 2]
		port_m, kv = results[i * 2 + 1]
		assert port_t == "test"
		assert port_m == "model"
		assert variant.key == f"t1#{i}"
		assert variant.model == "sandbox"  # name string — not ModelConfig
		assert kv.key == f"t1#{i}"
		assert kv.value == model.value  # same resolved ModelConfig


def test_expand_sweep_script_sees_resolved_model(tmp_path):
	script = tmp_path / "sweep.py"
	script.write_text(
		"model_name = test_cfg.model.get_model_name()\n"  # AttributeError if model is still a str
		"import dataclasses\n"
		"out_test_cfgs.append(dataclasses.replace(test_cfg))\n"
	)
	test = _make_test("t1", sweep_path=str(script))
	model = _make_sweep_model(test.key, name="sandbox")
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert test.model == "sandbox"  # name string restored after exec
	test_ports = [ v for p, v in results if p == "test" ]
	assert len(test_ports) == 1


def test_expand_sweep_script_raises(tmp_path, logging_handler):
	script = tmp_path / "sweep.py"
	script.write_text("raise RuntimeError('boom')\n")
	test = _make_test("t1", sweep_path=str(script))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True
	assert test.model == "sandbox"


def test_expand_sweep_script_not_found(tmp_path, logging_handler):
	test = _make_test("t1", sweep_path=str(tmp_path / "nonexistent.py"))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file-mode enforcement, so chmod 0o000 grants no denial")
def test_expand_sweep_script_permission_error(tmp_path, logging_handler):
	script = tmp_path / "sweep.py"
	script.write_text("pass\n")
	script.chmod(0o000)
	test = _make_test("t1", sweep_path=str(script))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	try:
		results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	finally:
		script.chmod(0o644)
	assert len(results) == 0
	assert logging_handler.failure is True


def test_expand_sweep_script_read_oserror(tmp_path, logging_handler):
	sweep_dir = tmp_path / "sweep_dir"
	sweep_dir.mkdir()
	test = _make_test("t1", sweep_path=str(sweep_dir))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_expand_sweep_empty_variants(tmp_path):
	script = tmp_path / "sweep.py"
	script.write_text("pass\n")  # out_test_cfgs stays empty
	test = _make_test("t1", sweep_path=str(script))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0


def test_expand_sweep_non_iterable_out_test_cfgs(tmp_path, logging_handler):
	script = tmp_path / "sweep.py"
	script.write_text("out_test_cfgs = 42\n")
	test = _make_test("t1", sweep_path=str(script))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_expand_sweep_variant_rejects_key_assignment(tmp_path, logging_handler):
	script = tmp_path / "sweep.py"
	script.write_text("out_test_cfgs.append(object())\n")
	test = _make_test("t1", sweep_path=str(script))
	model = _make_sweep_model(test.key)
	root_cfg = _make_sweep_root_cfg()
	mod = ExpandSweepMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True
