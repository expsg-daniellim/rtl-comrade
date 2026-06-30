import dataclasses
import os
import random
from pathlib import Path

import structlog

from modules.rtl_buddy.schema import KeyedValue, SeedMode, TestResult, RtlBuilderConfig, Command, Proc, RandSeed, RandSeedDone
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


class WriteRandseedMod:
    def run(self, randseed:RandSeed, proc:Proc, work_dir:Path):  # proc joined as a completion gate (rc unread); work_dir persistent
        try:
            Path(randseed.randseed_path).write_text(f"{randseed.seed}\n")
            if "hier_inst_seed" in randseed.argv:  # rtl_buddy membership check against the sim argv
                with open(Path(work_dir) / "HierInstanceSeed.txt") as f, Path(randseed.randseed_path).open("a") as out:
                    out.writelines(f)  # read from work_dir (where the sim dropped it), not ambient CWD (rtl_buddy vlog_sim.py:263-269 parity)
        except OSError as e:  # FileNotFoundError (missing HierInstanceSeed.txt) is an OSError subclass
            log.error("randseed_write_failed", key=randseed.key, path=randseed.randseed_path, exc_info=e)
        return ("randseed_done", RandSeedDone(randseed.key))  # ordering signal emitted regardless, so link-latest can't dangle


def force_symlink(target, link_name) -> None:
    tmp = f"{link_name}.{os.getpid()}.tmp"
    os.symlink(target, tmp)
    os.replace(tmp, link_name)  # atomic rename over any existing link (or absent target)


class LinkLatestMod:
    def run(self, randseed: RandSeed, proc: Proc, randseed_done: RandSeedDone, work_dir: Path):  # randseed_done: ordering gate (after write-randseed); unread. work_dir persistent
        force_symlink(proc.stdout_path, Path(work_dir) / "test.log")
        force_symlink(proc.stderr_path, Path(work_dir) / "test.err")
        force_symlink(randseed.randseed_path, Path(work_dir) / "test.randseed")
