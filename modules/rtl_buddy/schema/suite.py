from dataclasses import dataclass
from pathlib import Path

import structlog
from serde import serde

from .uvm import UVMConfig

log = structlog.get_logger()


@serde
@dataclass
class TestbenchConfig:
    """Configuration for a single testbench within a test suite."""

    __test__ = False  # domain type, not a pytest test class despite the Test* name

    name:str
    filelist:list[str]

    def get_name(self) -> str:
        """Return the testbench name."""

        return self.name

    def get_filelist(self) -> list[str]:
        """Return the testbench filelist."""

        return self.filelist


@dataclass
class TestConfig:
    """Mutable per-test runtime configuration carried on the test edge."""

    __test__ = False  # domain type, not a pytest test class despite the Test* name

    name:str
    desc:str
    model:str
    model_path:str
    suite_dir:Path
    reglvl:int | dict | None
    pa:dict | None
    pd:dict | None
    uvm:UVMConfig | None
    preproc_path:str | None
    postproc_path:str | None
    sweep_path:str | None
    tb:TestbenchConfig
    timeout:int | None
    default_timeout:int = 60
    key:str = ""

    def __post_init__(self):
        if not self.key:
            self.key = self.name

    def get_name(self) -> str:
        """Return the test name."""

        return self.name

    def get_testbench(self) -> TestbenchConfig:
        """Return the associated testbench configuration."""

        return self.tb

    def get_plusarg(self, key):
        """Return a single plusarg value. Raises AttributeError if pa is None."""

        return self.pa.get(key)

    def get_plusargs(self) -> dict | None:
        """Return the plusargs dict, or None if unset."""

        return self.pa

    def set_plusarg(self, key, value) -> None:
        """Set a single plusarg, lazily initialising pa if None."""

        if self.pa is None:
            self.pa = {}
        self.pa[key] = value

    def set_plusargs(self, new_args) -> None:
        """Merge new_args into pa, lazily initialising if None."""

        if self.pa is None:
            self.pa = {}
        self.pa.update(new_args)

    def get_plusdefine(self, key):
        """Return a single plusdefine value. Raises AttributeError if pd is None."""

        return self.pd.get(key)

    def get_plusdefines(self) -> dict | None:
        """Return the plusdefines dict, or None if unset."""

        return self.pd

    def set_plusdefine(self, key, value) -> None:
        """Set a single plusdefine, lazily initialising pd if None."""

        if self.pd is None:
            self.pd = {}
        self.pd[key] = value

    def set_plusdefines(self, new_defines) -> None:
        """Merge new_defines into pd, lazily initialising if None."""

        if self.pd is None:
            self.pd = {}
        self.pd.update(new_defines)

    def get_timeout(self) -> tuple[int, bool]:
        """Return (timeout, is_custom). Uses default_timeout when timeout is None."""

        is_custom = self.timeout is not None
        return self.timeout if is_custom else self.default_timeout, is_custom

    def set_timeout(self, timeout) -> None:
        """Set the simulation timeout."""

        self.timeout = timeout

    def get_sweep_path(self) -> str | None:
        """Return the sweep script path."""

        return self.sweep_path

    def get_preproc_path(self) -> str | None:
        """Return the pre-processing script path."""

        return self.preproc_path

    def get_postproc_path(self) -> str | None:
        """Return the post-processing script path."""

        return self.postproc_path

    def get_reglvl(self, builder:str) -> int:
        """Resolve the regression level for a given builder."""

        match self.reglvl:
            case int() as lvl:
                reglvl = lvl
            case dict() if builder in self.reglvl:
                reglvl = self.reglvl[builder]
            case dict() if "default" in self.reglvl:
                reglvl = self.reglvl["default"]
            case None:
                reglvl = 0
            case _:
                log.fatal("malformed_reglvl", test=self.name, builder=builder)
        return reglvl


@dataclass
class SuiteConfig:
    """Runtime suite configuration produced by parse-suite-config."""

    path:Path
    tests:dict[str, TestConfig]

    def get_tests(self, test_name=None):
        """Return tests — one-element list if test_name given, dict_values otherwise."""

        if test_name is not None:
            if test_name not in self.tests:
                log.fatal("test_not_found", test_name=test_name, suite=str(self.path))
            return [self.tests[test_name]]
        return self.tests.values()

    def get_test_names(self) -> list[str]:
        """Return all test names in declaration order."""

        return list(self.tests.keys())

    def get_path(self) -> Path:
        """Return the suite config path."""

        return self.path
