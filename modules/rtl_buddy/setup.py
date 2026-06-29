from pathlib import Path
from serde import serde
import structlog

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
