import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from serde import field, serde, SerdeError
from serde.yaml import from_yaml
from yaml.error import MarkedYAMLError
from yaml.reader import ReaderError
import structlog

from rtl_comrade.logging import HarnessLogger

from modules.rtl_buddy.schema import PlatformConfig, RootConfig, RootRtlField, RtlBuilderConfig, UVMConfig, TestbenchConfig, TestConfig, SuiteConfig, SeedMode, KeyedValue, ModelConfig

log:HarnessLogger = cast(HarnessLogger, structlog.get_logger())


class DiscoverConfigFileMod:
	@serde
	class Config:
		filename:str
		max_levels:int = 8

	def __init__(self, config):
		self.filename = config.filename
		self.max_levels = config.max_levels

	def run(self):  # pylint: disable=inconsistent-return-statements
		d = Path.cwd()
		try:
			for _ in range(self.max_levels):
				if (d / self.filename).is_file():
					return ("default", d / self.filename)
				if d == d.parent:  # filesystem root
					break
				d = d.parent
		except PermissionError as e:
			log.fatal("config_discovery_denied", filename=self.filename, dir=str(d), exc_info=e)
		log.fatal("config_not_found", filename=self.filename)


class PrependCwdPathMod:
	def run(self):
		parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
		if "." not in parts:
			os.environ["PATH"] = os.pathsep.join(["."] + parts)
		return ("default", True)


@serde
@dataclass
class RootConfigFile:
	filetype:Literal['project_root_config'] = field(rename='rtl-buddy-filetype')
	cfg_rtl_reg:RootRtlField = field(rename='cfg-rtl-reg')
	builders:list[RtlBuilderConfig] = field(rename='cfg-rtl-builder')
	platforms:list[PlatformConfig] = field(rename='cfg-platforms')


class ParseRootConfigMod:
	def run(self, path:Path):  # pylint: disable=inconsistent-return-statements
		try:
			raw = from_yaml(RootConfigFile, path.read_text())
			root_cfg = RootConfig(platforms=raw.platforms, rtl_builder_cfgs={c.get_name(): c for c in raw.builders}, cfg_rtl_reg=raw.cfg_rtl_reg)
			return ("default", root_cfg)
		except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError, OSError) as e:
			log.fatal(f"failed to load {path}: {e}")
		except (SerdeError, MarkedYAMLError, ReaderError) as e:
			log.fatal(f"failed to load {path}: {e}")


class SelectPlatformMod:
	def run(self, root_cfg:RootConfig):  # pylint: disable=inconsistent-return-statements
		try:
			uname = subprocess.run(["uname"], capture_output=True, text=True, check=True).stdout.strip()
		except FileNotFoundError as e:
			log.fatal("uname_unavailable", exc_info=e)
		except subprocess.CalledProcessError as e:
			log.fatal("uname_failed", exc_info=e)
		for platform_cfg in root_cfg.platforms:
			if uname in platform_cfg.unames:
				return ("default", platform_cfg)
		log.fatal(f"cannot find cfg-platform for uname {uname}")


class ResolveBuilderMod:
	def run(self, root_cfg:RootConfig, platform_cfg:PlatformConfig, builder:str = ""):
		name = builder or platform_cfg.builder
		builder_cfg = root_cfg.rtl_builder_cfgs.get(name)
		if builder_cfg is None:
			log.fatal(f"named builder {name} not in configured builders {sorted(root_cfg.rtl_builder_cfgs)}")
		return ("default", builder_cfg)


class WorkDirMod:
	def run(self):
		return ("default", Path.cwd().resolve())


class EnsureLogsDirMod:
	def run(self, work_dir:Path, logs_dir:str = "logs"):
		path = Path(work_dir) / logs_dir
		try:
			path.mkdir(parents=True, exist_ok=True)
		except OSError as e:
			log.fatal("logs_dir_create_failed", path=str(path), exc_info=e)
		log.info("logs_dir_ready", path=str(path.resolve()))
		return ("logs_dir", path)


@serde
@dataclass
class TestConfigFile:  # pylint: disable=too-many-instance-attributes
	name:str
	desc:str
	model:str
	model_path:str
	tb:str = field(rename='testbench')
	reglvl:int | dict | None = field(default=None)
	pa:dict | None = field(default=None, rename='plusargs')
	pd:dict | None = field(default=None, rename='plusdefines')
	uvm:UVMConfig | None = field(default=None)
	preproc_path:str | None = field(default=None, rename='preproc', deserializer=lambda data: data.get('path') if data is not None else None)
	postproc_path:str | None = field(default=None, rename='postproc', deserializer=lambda data: data.get('path') if data is not None else None)
	sweep_path:str | None = field(default=None, rename='sweep', deserializer=lambda data: data.get('path') if data is not None else None)
	timeout:int | None = field(default=None, rename='sim_timeout')


@serde
@dataclass
class SuiteConfigFile:
	filetype:Literal['test_config'] = field(rename='rtl-buddy-filetype')
	testbenches:list[TestbenchConfig]
	tests:list[TestConfigFile]


class ParseSuiteConfigMod:
	def run(self, test_config:str = "tests.yaml"):
		path = Path(test_config).resolve()
		try:
			raw = from_yaml(SuiteConfigFile, path.read_text(encoding="utf-8"))
		except UnicodeDecodeError as e:
			log.fatal("invalid_unicode", path=str(path), reason=e.reason, exc_info=e)
		except FileNotFoundError as e:
			log.fatal("not_found", path=str(path), exc_info=e)
		except IsADirectoryError as e:
			log.fatal("is_directory", path=str(path), exc_info=e)
		except PermissionError as e:
			log.fatal("permission_denied", path=str(path), exc_info=e)
		except OSError as e:
			log.fatal("os_error", path=str(path), err=e.strerror, errno=e.errno, exc_info=e)
		except SerdeError as e:
			log.fatal("serde_error", path=str(path), message=str(e), exc_info=e)
		except MarkedYAMLError as e:
			log.fatal("yaml_invalid", path=str(path), problem=e.problem, exc_info=e)
		except ReaderError as e:
			log.fatal("yaml_unreadable", path=str(path), reason=e.reason, exc_info=e)
		except ValueError as e:
			log.fatal("invalid_uvm_config", path=str(path), reason=str(e), exc_info=e)
		tbs = { tb.get_name(): tb for tb in raw.testbenches }
		tests = {}
		for t in raw.tests:
			try:
				tb = tbs[t.tb]
			except KeyError as e:
				log.fatal("unknown_testbench", path=str(path), test=t.name, testbench=t.tb, exc_info=e)
			tests[t.name] = TestConfig(name=t.name, desc=t.desc, model=t.model, model_path=t.model_path, reglvl=t.reglvl, pa=t.pa, pd=t.pd, uvm=t.uvm, preproc_path=t.preproc_path, postproc_path=t.postproc_path, sweep_path=t.sweep_path, tb=tb, timeout=t.timeout, suite_dir=path.parent)
		suite_cfg = SuiteConfig(path=path, tests=tests)
		return ("default", suite_cfg)


class DeriveSeedModeMod:
	def run(self, rnd_new:bool = False, rnd_last:bool = False):
		mode = SeedMode.DEFAULT
		if rnd_new:
			mode = SeedMode.NEW
		elif rnd_last:
			mode = SeedMode.REPLAY
		return ("default", mode)


class RouteListModeMod:
	def run(self, suite_cfg:SuiteConfig, list_:bool = False):
		if list_:
			return ("list", suite_cfg)
		return ("run", suite_cfg)


class ListTestNamesMod:
	def run(self, suite_cfg:SuiteConfig):
		print("  ".join(suite_cfg.get_test_names()))


class SelectTestsMod:
	def run(self, suite_cfg:SuiteConfig, test_name:str = ""):
		for t in suite_cfg.get_tests(test_name or None):
			yield ("test", t)


class FilterRegLvlMod:
	def run(self, test:TestConfig, builder_cfg:RtlBuilderConfig, reg_level:int | None = None, start_level:int | None = None):
		lvl = test.get_reglvl(builder_cfg.get_name())
		if reg_level is not None and lvl > reg_level:
			desc = f"lvl {lvl} > cmd end_level {reg_level}"
		elif start_level is not None and lvl < start_level:
			desc = f"lvl {lvl} < cmd start_level {start_level}"
		else:
			return ("test", test)
		log.info("test_skipped", key=test.key, test_name=test.get_name(), reason=desc)


@serde
@dataclass
class ModelConfigFileItem:
	name:str
	filelist:list[str]


@serde
@dataclass
class ModelConfigFile:
	filetype:Literal['model_config'] = field(rename='rtl-buddy-filetype')
	models:list[ModelConfigFileItem] = field(default_factory=list)


class ResolveModelRefMod:
	def run(self, test:TestConfig):
		yield ("model_name", KeyedValue(test.key, test.model))
		yield ("model_path", KeyedValue(test.key, test.suite_dir / test.model_path))


class LoadModelMod:
	def run(self, model_name:str, model_path:Path, test:TestConfig|None = None):
		key = test.key if test is not None else model_name
		test_name = test.get_name() if test is not None else None
		try:
			with open(model_path, encoding="utf-8") as f:
				file = from_yaml(ModelConfigFile, f.read())
			item = next((m for m in file.models if m.name == model_name), None)
			if item is None:
				raise LookupError(f"model {model_name!r} not in {model_path}")
			yield ("model", ModelConfig(name=item.name, filelist=item.filelist, path=str(model_path)))
		except FileNotFoundError:
			log.error("model_file_not_found", key=key, test_name=test_name, model_path=str(model_path))
		except IsADirectoryError:
			log.error("model_is_directory", key=key, test_name=test_name, model_path=str(model_path))
		except PermissionError as e:
			log.error("model_permission_denied", key=key, test_name=test_name, model_path=str(model_path), err=e.strerror)
		except UnicodeDecodeError as e:
			log.error("model_invalid_unicode", key=key, test_name=test_name, model_path=str(model_path), reason=e.reason)
		except (SerdeError, MarkedYAMLError, ReaderError) as e:
			log.error("model_parse_error", key=key, test_name=test_name, model_path=str(model_path), err=str(e))
		except LookupError:
			log.error("model_not_found", key=key, test_name=test_name, model_path=str(model_path), model=model_name)
		except OSError as e:
			log.error("model_read_error", key=key, test_name=test_name, model_path=str(model_path), err=e.strerror, errno=e.errno)


class ExpandSweepMod:
	def run(self, test:TestConfig, model:KeyedValue, root_cfg:RootConfig):
		sweep = test.get_sweep_path()
		if sweep is None:
			yield ("test", test)
			yield ("model", model)
			return
		name = test.model
		ns = {"logger": log, "TestConfig": TestConfig, "test_cfg": test, "root_cfg": root_cfg, "out_test_cfgs": []}
		try:
			with open(sweep, encoding="utf-8") as f:
				code = f.read()
		except FileNotFoundError:
			log.error("sweep_script_not_found", key=test.key, test_name=test.get_name(), sweep_path=str(sweep))
			return
		except PermissionError as e:
			log.error("sweep_script_permission", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), err=e.strerror)
			return
		except OSError as e:
			log.error("sweep_script_read_error", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), err=e.strerror, errno=e.errno)
			return
		test.model = model.value
		try:
			exec(compile(code, sweep, "exec"), ns)  # pylint: disable=exec-used  # runs user sweep script, rtl_buddy parity
		except Exception as e:
			test.model = name
			log.error("sweep_script_error", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), exc_info=e)
			return
		test.model = name
		try:
			for i, variant in enumerate(ns["out_test_cfgs"]):
				variant.key = f"{test.key}#{i}"
				variant.model = name
				yield ("test", variant)
				yield ("model", KeyedValue(variant.key, model.value))
		except (TypeError, AttributeError, KeyError) as e:
			log.error("sweep_output_invalid", key=test.key, test_name=test.get_name(), sweep_path=str(sweep), err=str(e))


class GitStatusMod:
	def run(self):
		try:
			branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
			sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
			dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.strip())
			log.info("git_state", branch=branch, sha=sha, dirty=dirty)
		except (subprocess.CalledProcessError, FileNotFoundError) as e:
			log.warning("git_state_unavailable", reason=str(e))
		return ("default", True)
