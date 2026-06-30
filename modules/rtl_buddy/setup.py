import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from serde import field, serde, SerdeError
from serde.yaml import from_yaml
from yaml.error import MarkedYAMLError
from yaml.reader import ReaderError
import structlog

from modules.rtl_buddy.schema import PlatformConfig, RootConfig, RootRtlField, RtlBuilderConfig

log = structlog.get_logger()


class DiscoverConfigFileMod:
    @serde
    class Config:
        filename:str
        max_levels:int = 8

    def __init__(self, config):
        self.filename = config.filename
        self.max_levels = config.max_levels

    def run(self):
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
    def run(self, path:Path):
        try:
            raw = from_yaml(RootConfigFile, path.read_text())
            root_cfg = RootConfig(platforms=raw.platforms, rtl_builder_cfgs={c.get_name(): c for c in raw.builders}, cfg_rtl_reg=raw.cfg_rtl_reg)
            return ("default", root_cfg)
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError, OSError) as e:
            log.fatal(f"failed to load {path}: {e}")
        except (SerdeError, MarkedYAMLError, ReaderError) as e:
            log.fatal(f"failed to load {path}: {e}")


class SelectPlatformMod:
    def run(self, root_cfg:RootConfig):
        try:
            uname = subprocess.run(["uname"], capture_output=True, text=True).stdout.strip()
        except FileNotFoundError as e:
            log.fatal("uname_unavailable", exc_info=e)
        for platform_cfg in root_cfg.platforms:
            if uname in platform_cfg.unames:
                return ("default", platform_cfg)
        log.fatal(f"cannot find cfg-platform for uname {uname}")
