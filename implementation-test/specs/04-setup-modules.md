# Spec 04: Setup modules

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md)
(`ParseSuiteConfigMod` produces `SuiteConfig` / `TestConfig` / `TestbenchConfig`).
**References:** [03 — Setup section](../03-module-catalog.md).

## Goal

Implement the run-once setup chain that reimplements rtl_buddy's `RootConfig` /
`SuiteConfig` orchestration as six atomic nodes plus a CWD-convention guard, a
logs-directory bootstrap, and the trivial seed-mode derivation.

## Deliverables

In `modules/rtl_test/setup.py`:

- `DiscoverConfigFileMod` — walks up the dir tree from CWD for a filename (config:
  `filename:str`, `max_levels:int = 8`); stops at git root or filesystem root; emits the
  resolved `Path`. Zero input ports; runs once via `unit`.
  **Failure handling**: post-loop check — if walked to the root without finding the file,
  call `log.critical(f"{filename} not found walking up from CWD")` (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:35`). `PermissionError` from directory listing
  propagates uncaught (becomes harness CRITICAL via the bubbling-SystemExit catch). See
  [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
- `PrependCwdPathMod` — prepends `.` to `os.environ["PATH"]` so a CWD-local simulator
  (`simv`, `verilator`) is discoverable by subsequent subprocess invocations. Mirrors
  `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102`, which does the same once at CLI
  bootstrap; here it is an explicit graph node so the responsibility is visible. Zero
  input ports; runs once via `unit`. Emits `True` on `default`; the value is consumed by
  `run-process` as a `env_ready` sequencing input (see [07 settled
  25](../07-ambiguities-and-assumptions.md)).
  **Behaviour**:
  1. `path = os.environ.get("PATH", "")`
  2. If `"." not in path.split(os.pathsep)`: `os.environ["PATH"] = "." + os.pathsep + path`.
  3. Return `{"default": True}`.
  Idempotent — re-invocation (or a stale `.` already on PATH) is a no-op. Mutation of
  the process-wide `os.environ` is safe because `unit` guarantees a single invocation.
  **Failure handling**: none. Dict mutation cannot meaningfully fail; no failure port,
  no log call.
- `ParseRootConfigMod` — reads the path, deserialises into the schema (spec 01); emits
  `root_cfg`.
  **Failure handling**: catch broad `Exception` from the YAML load (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:88-89`). Specific classes in play:
  `FileNotFoundError`, `PermissionError`, `IsADirectoryError` (file I/O);
  `serde.SerdeError` or `yaml.YAMLError` (parse); `TypeError` / `KeyError` (schema /
  dataclass mismatch). Convert to `log.critical(f"failed to load {path}: {e}")`.
- `SelectPlatformMod` — runs `uname` (subprocess), matches against each platform's
  `unames`, picks one; critical-logs if no match; emits `platform_cfg`.
  **Failure handling**: post-loop check — no platform matched → `log.critical(f"cannot
  find cfg-platform for uname {uname}")` (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:117-118`). `uname` subprocess failure is
  surprising at this layer; let `FileNotFoundError` propagate.
- `ResolveBuilderMod` — picks the active `RtlBuilderConfig` from `platform_cfg` honouring
  the CLI `builder` override; critical-logs on unknown override; emits `builder_cfg`.
  **Failure handling**: post-lookup check — if `builder` override is non-empty and not in
  the platform's `cfg-rtl-builder` list, `log.critical(f"named builder {builder} not in
  configured builders {sorted(...)}")` (rtl_buddy's `rtl_buddy.py:76-80` raises
  `typer.BadParameter`; Plan B uses log.critical for uniform exit semantics). Empty list
  (`no builders configured`) is also `log.critical` (`root.py:151`).
- `CheckSuiteCwdMod` — validates the user-driven CWD convention: `rtl-comrade test` /
  `randtest` must be invoked from the suite directory (matching rtl_buddy's `do_cmd_test`,
  which never `chdir`s — see `rtl_buddy/AGENTS.md` validation example: `cd .../verif &&
  python -m rtl_buddy test basic`). Takes the CLI `test_config:str` and resolves it
  against CWD; emits the resolved `Path` that downstream `ParseSuiteConfigMod` consumes.
  **Behaviour**:
  1. `resolved = (Path.cwd() / test_config).resolve()`; `cwd = Path.cwd().resolve()`.
  2. If `resolved.parent != cwd` → `log.critical(f"test_config {test_config!r} resolves
     to {resolved}, which is not in the current directory ({cwd}). Run rtl-comrade test
     from the suite directory.")` — catches `-c /abs/elsewhere/tests.yaml`,
     `-c ../sibling/tests.yaml`, and `-c subdir/tests.yaml`, which would otherwise parse
     fine but silently mistarget `logs/`, `run.f`, `obj_dir_<tag>/`, and the `test.*`
     symlinks to the wrong directory.
  3. If `not resolved.is_file()` → `log.critical(f"test_config {test_config!r} not found
     at {resolved}")`.
  4. Emit `resolved` on `default`.
  Both `.resolve()` calls follow symlinks symmetrically, so a `tests.yaml` symlink in a
  symlinked CWD passes correctly.
  **Failure handling**: both checks are setup-domain config errors → `log.critical` (see
  [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site)).
- `EnsureLogsDirMod` — bootstraps the CWD-relative artefact directory consumed by
  `cc-run`, `sim-run`, `write-randseed`, and `resolve-seed` (REPLAY). Mirrors
  `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` (`output_dir = "logs"; if not
  os.path.exists(...): os.makedirs(...)`), but lifted out of `VlogSim.__init__`'s
  per-test lazy mkdir into a single explicit setup node so:
  (i) no downstream writer needs its own `mkdir`, and
  (ii) the directory is created exactly once per invocation, ahead of any subprocess.
  Takes the CLI `logs_dir:str` (default `"logs"`; `rtl_buddy` has no override, this is a
  small Notable divergence — see [07](../07-ambiguities-and-assumptions.md)), plus two
  sequencing inputs: `env_ready:bool` from `prepend-cwd-path` (so the `$PATH` mutation
  precedes us) and `_cwd:Path` from `check-suite-cwd` (so we never create `logs/` in an
  invalid CWD that the check would have aborted). Zero side-effects on the latter — it
  is consumed solely for data-edge ordering. Runs once via `unit`.
  **Behaviour**:
  1. `Path(logs_dir).mkdir(parents=True, exist_ok=True)` — idempotent; `parents=True`
     accepts nested paths (e.g., `build/logs`).
  2. `log.info("logs_dir_ready", path=str(Path(logs_dir).resolve()))` for auditability.
  3. Return `{"default": True}` so `cc-run.env_ready` and `sim-run.env_ready` can chain
     off the same sequencing surface as PATH-prepend (see [07 settled 25 / 26](../07-ambiguities-and-assumptions.md)).
  Path is **not** resolved-and-stamped into `ctx`. Downstream paths (`logs/<test>.compile.log`,
  `logs/<test>[_NNNN].log`/`.err`/`.randseed`) are composed in `build-compile-cmd` /
  `build-sim-cmd` / `resolve-seed` / `write-randseed` from the same `logs_dir` persistent
  input, so the path joins happen at the use site.
  **Failure handling**: `PermissionError` / `OSError` from `mkdir` propagate uncaught
  (becomes a harness CRITICAL via the bubbling-SystemExit catch, same idiom as
  `DiscoverConfigFileMod`'s `PermissionError`). No port-routed fail — this is a setup-domain
  config error, not per-test.

- `ParseSuiteConfigMod` — reads `test_config:Path` (the resolved path from
  `CheckSuiteCwdMod` in test/randtest graphs, or from `parse-reg-config` in regression),
  deserialises into `SuiteConfigFile` (spec [01b](01b-suite-schema.md)), binds each
  raw `TestConfigFile.tb` (YAML `testbench`) to the corresponding `TestbenchConfig`
  in-file via the `tbs = {tb.get_name(): tb for tb in raw.testbenches}` dict, stamps
  `suite_dir = test_config.parent` onto each test (so `load-model` in spec
  [05](05-selection-expansion-modules.md) can resolve `suite_dir / test.model_path`),
  and emits `suite_cfg: SuiteConfig` (`tests: dict[str, TestConfig]`, `path: Path`).
  **Module is contract-agnostic** — pairs with `unit` in test/randtest graphs,
  `default` in regression (see [08](../08-sibling-graphs.md)). The constructor flow
  (open → `from_yaml` → bind testbenches → `initialise` each test) is enumerated in
  spec [01b — `SuiteConfig`](01b-suite-schema.md).
  **Failure handling**: catch broad `Exception` from the YAML load and from
  `UVMConfig.__post_init__`'s `ValueError` on negative `max_warns`/`max_errors` (same
  exception family as `ParseRootConfigMod`) → `log.critical`. After deserialisation, a
  post-check: each `TestConfigFile.tb` must resolve to a defined `TestbenchConfig` —
  unresolved (`KeyError` from `tbs[t.tb]`) → `log.critical(f"test {test.name}
  references unknown testbench {test.tb}")`. Mirrors `rtl_buddy/src/rtl_buddy/config/suite.py:28-50`.
- `DeriveSeedModeMod` — `(rnd_new:bool=False, rnd_last:bool=False)` → `SeedMode` (`rnd_new`
  wins, else `REPLAY` if `rnd_last`, else `DEFAULT`). No failure path.

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

Tests in `modules/tests/test_setup.py`:
- Discovery walks up to find a fixture `root_config.yaml`; stops at depth limit.
- Prepend-cwd-path: with a `PATH` that does not contain `.`, `run()` mutates
  `os.environ["PATH"]` to start with `. + os.pathsep` and returns `{"default": True}`.
- Prepend-cwd-path: with a `PATH` that already starts with `.`, `run()` leaves it
  unchanged and still returns `{"default": True}` (idempotent).
- Prepend-cwd-path: with a `PATH` that contains `.` somewhere in the middle, `run()`
  leaves it unchanged (not just the head position counts).
- Prepend-cwd-path: end-to-end with `run-process` — after `PrependCwdPathMod.run()`
  fires, a `RunProcessMod.run()` call with `argv=["./local_tool"]` (a script written
  into the temp CWD with the exec bit set) resolves and executes the binary, where
  the same call would fail with `FileNotFoundError` if the prepend had not happened.
  Restore `os.environ["PATH"]` in the test fixture teardown.
- Parse round-trips an unmodified rtl_buddy `root_config.yaml`.
- Platform select picks correctly under controlled `uname` (mock or skip-if).
- Builder resolve honours override; critical on bad name.
- Check-cwd: `tests.yaml` in CWD → emits resolved Path; bare filename matching
  `Path.cwd() / "tests.yaml"`.
- Check-cwd: `-c /abs/elsewhere/tests.yaml` → `log.critical` with CWD-mismatch message.
- Check-cwd: `-c ../sibling/tests.yaml` → `log.critical` (parent is not CWD).
- Check-cwd: `-c subdir/tests.yaml` → `log.critical` (parent is a subdir of CWD, not CWD).
- Check-cwd: missing file in CWD → `log.critical` with not-found message.
- Check-cwd: CWD itself is a symlink (e.g., `/tmp/link → /tmp/real`) and `tests.yaml`
  sits in `/tmp/real` → passes (both `.resolve()` calls collapse to the same realpath).
- Ensure-logs-dir: with `logs_dir="logs"` and no pre-existing `logs/` → `run()` creates
  `logs/` under CWD and returns `{"default": True}`.
- Ensure-logs-dir: with a pre-existing `logs/` directory → `run()` is a no-op and still
  returns `{"default": True}` (idempotent, no exception).
- Ensure-logs-dir: with `logs_dir="build/logs"` and no pre-existing `build/` → `run()`
  creates both `build/` and `build/logs/` (verifies `parents=True`).
- Ensure-logs-dir: with `logs_dir="/abs/path/logs"` (absolute) → `run()` creates the
  absolute path; `cc-build` / `sim-build` downstream compose the same prefix.
- Ensure-logs-dir: with `logs_dir` pointing into a read-only parent → `PermissionError`
  propagates uncaught (mirrors the `DiscoverConfigFileMod` PermissionError test).
- Suite parse handles a real rtl_buddy `tests.yaml` (input now a `Path`, not a `str`).

## Acceptance criteria

- Tests pass.
- An end-to-end "setup-only" graph that wires these nine nodes produces correct
  `root_cfg`/`builder_cfg`/`suite_cfg` values from real rtl_buddy fixtures, with
  `CheckSuiteCwdMod` aborting fixture runs invoked from outside the suite directory,
  `PrependCwdPathMod` leaving `os.environ["PATH"]` starting with `.` for the
  duration of the run, and `EnsureLogsDirMod` leaving the configured `logs_dir`
  present on disk (default `./logs/`) before any later main-line node fires.

## Notes

`DiscoverConfigFileMod` is reusable for the harness's own config discovery — see [07
implementation note](../07-ambiguities-and-assumptions.md). `DeriveSeedModeMod` is on the
KIV path (item 18) — keep it small and stateless; future absorbing into `resolve-seed`
should be straightforward. `CheckSuiteCwdMod` is the explicit enforcement of the
user-driven CWD convention documented in [01](../01-cli-and-entry.md) — the regression
graph does **not** wire it (regression `chdir`s per-suite internally; see
[08](../08-sibling-graphs.md)). `EnsureLogsDirMod` is wired in `test`/`randtest` only
for the same reason: regression's per-suite `chdir` means a once-at-startup `logs/`
bootstrap targets the wrong place; the regression equivalent runs **per chdir'd suite**
and is owned by [08](../08-sibling-graphs.md).
