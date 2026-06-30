import dataclasses
import random
from pathlib import Path

import structlog

from modules.rtl_buddy.schema import KeyedValue, SeedMode, TestResult, RtlBuilderConfig, Command, RandSeed
from modules.rtl_buddy.schema.suite import TestConfig

log = structlog.get_logger()


class ExpandRunsMod:
    def run(self, test:TestConfig, simv:KeyedValue[str], run_ids:list = [None]):
        for run_id in run_ids:
            nk = test.key if run_id is None else f"{test.key}#{run_id}"
            yield ("test", dataclasses.replace(test, key=nk))
            yield ("run_id", KeyedValue(nk, run_id))
            yield ("simv", KeyedValue(nk, simv.value))


def run_suffix(run_id) -> str:
    return "" if run_id is None else f"_{run_id:04d}"  # run-id zero-padded to four digits


class ResolveSeedMod:
    def run(self, test:TestConfig, run_id:KeyedValue, simv:KeyedValue, seed_mode:SeedMode, builder_cfg:RtlBuilderConfig, logs_dir:Path):
        if seed_mode == SeedMode.NEW:
            seed = random.randrange(1_000_000)
        elif seed_mode == SeedMode.DEFAULT:
            seed = builder_cfg.get_seed()
        else:  # REPLAY
            path = logs_dir / f"{test.get_name()}{run_suffix(run_id.value)}.randseed"
            try:
                seed = int(Path(path).open().readline().strip())
            except FileNotFoundError:
                log.error("replay_seed_not_found", key=test.key, test_name=test.get_name(), path=str(path))
                yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}")); return
            except ValueError as e:
                log.error("replay_seed_malformed", key=test.key, test_name=test.get_name(), path=str(path), err=str(e))
                yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}")); return
            except PermissionError as e:
                log.error("replay_seed_permission", key=test.key, test_name=test.get_name(), path=str(path), err=e.strerror)
                yield ("fail", TestResult.prep(test.key, test.get_name(), f"Replay seed missing or invalid at {path}")); return
        yield ("test", test)
        yield ("run_id", run_id)
        yield ("simv", simv)
        yield ("seed", KeyedValue(test.key, seed))


class BuildSimCmdMod:
    def run(self, test:TestConfig, run_id:KeyedValue[int | None], simv:KeyedValue[str], seed:KeyedValue[int], builder_cfg:RtlBuilderConfig, builder_mode:str, logs_dir:Path):
        plusdefines = []
        pd = test.get_plusdefines()
        if pd is not None:
            for k, v in pd.items():
                plusdefines.append(f"+define+{k}={v}" if v is not None else f"+define+{k}")
        plusargs = []
        pa = test.get_plusargs()
        if pa is not None:
            for k, v in pa.items():
                plusargs.append(f"+{k}={v}" if v is not None else f"+{k}")
        argv = [simv.value, *builder_cfg.get_run_time_opts(builder_mode, seed=seed.value), *plusdefines, *plusargs]
        timeout, is_custom = test.get_timeout()
        if is_custom:
            log.warning("custom_sim_timeout", key=test.key, timeout=timeout)
        stem = logs_dir / f"{test.get_name()}{run_suffix(run_id.value)}"
        log_path, err_path, rs_path = f"{stem}.log", f"{stem}.err", f"{stem}.randseed"
        yield ("test", test)
        yield ("command", Command(test.key, argv=argv, stdout_path=log_path, stderr_path=err_path))
        yield ("timeout", KeyedValue(test.key, float(timeout)))
        yield ("randseed", RandSeed(test.key, seed=seed.value, randseed_path=rs_path, argv=argv))
