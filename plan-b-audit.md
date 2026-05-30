# Audit: Plan B (`implementation-test/`) vs rtl_buddy `test` command

## Section A — Reference-flow concern inventory

Citations refer to files under `rtl_buddy/src/rtl_buddy/`.

1. **Prepend `.` to `PATH`** so a CWD-local simulator binary is discoverable. `rtl_buddy.py:L100-L102`.
2. **Initialise logger handlers** — console (DEBUG/RESULT switched by `--debug`), `rtl_buddy.log` file handler, `PassFailFormatter` for color, custom `RESULT` level. `rtl_buddy.py:L125-L149`.
3. **`ExitHandler` escalates CRITICAL log records to `typer.Abort`.** `rtl_buddy.py:L32-L36`.
4. **Print `rtl_buddy v<version>` startup banner.** `rtl_buddy.py:L152`.
5. **`show_git_rev()` for git-aware commands (test, randtest, regression, filelist).** Prints branch, commit hash, mod/staged counts, both to console and into the log file. `rtl_buddy.py:L109-L113, L500-L522`.
6. **Discover `root_config.yaml`** by walking up the CWD (max 8 levels). `config/root.py:L16-L36`.
7. **Parse `root_config.yaml`** via serde into `RootConfigFile` with rtl_buddy-specific field renames (`rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`, `cfg-verible`, `cfg-rtl-reg`). `config/root.py:L42-L48, L83-L94`.
8. **Initialise reg-config** (`RegConfig` instance) eagerly from `root_config.yaml` even in plain `test` mode. `config/root.py:L100-L104`.
9. **Run `uname` subprocess and match platform** against each `PlatformConfig.unames`. `config/root.py:L107-L115`.
10. **Initialise platform** which validates verible config and resolves `RtlBuilderConfig` keyed by `PlatformConfigFile.builder`. `config/platform.py:L63-L84`.
11. **Validate `--builder` override** against the configured builder names in root_config (callback rejects unknown values). `rtl_buddy.py:L70-L80, config/platform.py:L71-L76`.
12. **Initialise verible configs** (kept but unused by `test`). `config/root.py:L96-L97`.
13. **Default `rtl_builder_mode` to `debug` if not set.** `rtl_buddy.py:L178`.
14. **Capture `--early-stop` / `RunDepth` global**. `rtl_buddy.py:L121, L160`. Phase order `PRE/COMP/SIM/POST`. `runner/test_runner.py:L14-L18`.
15. **Load `SuiteConfig` from `tests.yaml`** including the serde testbench/test deserialise, the `tbs` dict bind, and `config_dir` capture. `config/suite.py:L26-L50`.
16. **`--list` branch**: print all test names joined by two-spaces and exit 0. `rtl_buddy.py:L182-L184`.
17. **Derive `SeedMode`** from `rnd_new` / `rnd_last` (precedence: `rnd_new` wins, then `rnd_last`, else `DEFAULT`). `rtl_buddy.py:L189-L194`.
18. **`run_ids = [None]` in plain `test`.** `rtl_buddy.py:L188`.
19. **Test selection** by name (or all). `config/suite.py:L52-L67`. Critical on unknown test name.
20. **Regression-level filter window** (`start_level <= reglvl <= reg_level`); skipped tests get a per-`run_id` `SkipResults` row. `rtl_buddy.py:L350-L357, L259-L262`. (For plain `test`, both bounds default to `None` so no skipping happens.)
21. **`get_reglvl(builder)`** with int/dict/None handling and `default` fallback; critical on malformed. `config/test.py:L266-L299`.
22. **Sweep expansion** via `exec`'d Python script with namespace `{logger, TestConfig, test_cfg, root_cfg, out_test_cfgs}`. Exception → `logger.critical`. `rtl_buddy.py:L264-L283`.
23. **Per-test instantiation of `TestRunner`** with all config (note: `run_id=run_ids[0]` is passed even when there are multiple). `rtl_buddy.py:L285-L295`.
24. **One-shot vs run-multiple branching** based on `len(run_ids)`. `rtl_buddy.py:L297-L299`.
25. **Lazy load of models for each test** via `ModelConfigLoader(...).get_model(name)` invoked when `_write_filelist` runs. `tools/vlog_sim.py:L92`. Note: rtl_buddy actually loads models *eagerly* during `SuiteConfig.initialise` via `TestConfigFile.initialise`. `config/test.py:L320-L323`.
26. **Create per-test `logs/` directory.** `tools/vlog_sim.py:L55-L59`.
27. **Compute per-test build-tag, build-dir, simv path** (verilator vs other). `tools/vlog_sim.py:L61-L80`.
28. **Run `preproc` script** via `exec` if a `preproc_path` is set; namespace `{logger, test_cfg, root_cfg}`. `tools/vlog_sim.py:L119-L139`.
29. **Early-stop at `pre`** → `EarlyStopResults('Stopped early at preproc')`. `runner/test_runner.py:L59-L60`.
30. **Write filelist `run.f`** via `VlogFilelist.write_output(unroll=True, deduplicate=True, test_filelist=tb.get_filelist())`. `tools/vlog_sim.py:L88-L94`, `tools/vlog_filelist.py:L137-L159`.
31. **Filelist parsing rules** — handle `-v`, `-y`, `-F`/`-f`, `+incdir+`, `+libext+`, comment skip, `-F` recursion when unroll, `-f` is critical-rejected, `+libext+` consolidation, env var expansion, existence checks. `tools/vlog_filelist.py:L26-L135`.
32. **Compile argv assembly**: `[exe] + compile_time_opts(mode) + (["--Mdir", build_dir] if verilator) + plusdefines + ["-f", "run.f"]`. `tools/vlog_sim.py:L141-L159`.
33. **Plusdefines/plusargs formatting** (with vs without value). `tools/vlog_sim.py:L95-L117`.
34. **Compile subprocess (capture_output)** with elapsed-time print, error/debug log dump of stdout+stderr, critical on `FileNotFoundError`. `tools/vlog_sim.py:L161-L179`.
35. **Compile-fail short-circuit** → `CompileFailResults`. `runner/test_runner.py:L63-L65`.
36. **Early-stop at `comp`** → `EarlyStopResults('Stopped early at compile')`. `runner/test_runner.py:L67-L68`.
37. **Run-id loop** (for `run_multiple`); replay-run-id falls back to per-iteration run_id when `replay_run_id is None`. `runner/test_runner.py:L82-L117`, especially L106-L108.
38. **Seed resolution** — `DEFAULT` uses `builder_cfg.get_seed()`; `NEW` uses `random.randrange(1_000_000)`; `REPLAY` reads `logs/<test>[_NNNN].randseed`. `tools/vlog_sim.py:L191-L220`.
39. **Replay-missing/invalid handling**: writes a `FAIL replay seed missing` `.log`, an `.err` with the error message, force-symlinks `test.err`/`test.log`, returns `rc=1`. `tools/vlog_sim.py:L200-L212`.
40. **Sim argv assembly**: `[simv] + run_time_opts(mode, seed=…)` (which appends `sim_rand_seed_prefix + str(seed)`) + plusdefines + plusargs. `tools/vlog_sim.py:L220-L228`, `config/rtl.py:L104-L123`.
41. **Per-test timeout resolution** (`test.get_timeout()`) with warn-on-custom log line. `tools/vlog_sim.py:L232-L234`, `config/test.py:L210-L219`.
42. **Sim subprocess with redirects, process-group setup, SIGINT→SIGQUIT propagation, timeout enforcement, `rc=4444` sentinel on timeout.** `tools/vlog_sim.py:L240-L262`.
43. **Write `.randseed` file** (plus `HierInstanceSeed.txt` appended when present). `tools/vlog_sim.py:L263-L269`.
44. **Force `test.log`/`test.err`/`test.randseed` symlinks** in CWD to this run's files. `tools/vlog_sim.py:L271-L273, L26-L30`.
45. **Sim-timeout terminal result** (`rc==4444` → `SimTimeoutResults`). `runner/test_runner.py:L72-L73`.
46. **Early-stop at `sim`** → `EarlyStopResults('Stopped early at sim')`. `runner/test_runner.py:L75-L76`.
47. **Post dispatch on `test.uvm`**: `UvmVlogPost` if present, else `VlogPost`. `tools/vlog_sim.py:L283-L300`.
48. **`VlogPost` log scan**: `^PASS …` / `^FAIL …` / `^(ERR|FAT): …`; default NA; PASS wins; FAIL+ERR combined into desc. `tools/vlog_post.py:L23-L45`.
49. **`UvmVlogPost` UVM Report Summary parse**: extract WARNING/ERROR/FATAL counts, compare against `max_warns`/`max_errors` (FATAL must be 0). `tools/vlog_post.py:L48-L81`.
50. **Aggregate summary printing** via `logger.result(...)`, one line per `(test_name, randmode_i, result)`. `rtl_buddy.py:L203-L207`.
51. **OR-accumulated exit code** (`exit_code |= 0 if is_pass() else 1`). PASS/SKIP contribute 0; FAIL/NA contribute 1. `rtl_buddy.py:L206, runner/test_results.py:L29-L30`.
52. **`typer.Exit(exit_code)`** as the final exit mechanism. `rtl_buddy.py:L209`.
53. **Cleanup `\r` print line** after sim spinner output (`print(" "*80, end='\r', …)`). `rtl_buddy.py:L368`, `tools/vlog_sim.py:L178, L276`.
54. **Compile/sim elapsed-time spinner lines** to stdout (`\r`-suffixed). `tools/vlog_sim.py:L176-L178, L275-L276`.

## Section B — Module-to-concern coverage table

| # | rtl_buddy concern | Plan B module(s) | Coverage | Notes |
|---|---|---|---|---|
| 1 | Prepend `.` to PATH | `run-process` or `resolve-builder` (per 01-cli L52 and 07 impl note) | Partial | Mentioned in 01-cli-and-entry.md L50-L52 and 07 implementation notes as an obligation, but no module spec actually owns the work; not in `03-module-catalog.md` or specs 03/04 deliverables. |
| 2 | Logger handler init (file + console, color formatter, RESULT level) | (harness owned; `--debug`/`--color` dropped) | Out-of-scope-by-design | Settled 11 (07 L62-L64). `rtl_buddy.log` file + RESULT/PassFailFormatter coloring are dropped. |
| 3 | CRITICAL → abort | harness logging maps CRITICAL → SystemExit(1) | Full | Per `docs/invariants.md` and 07 settled 10. |
| 4 | Startup version banner | — | Missing | No module emits a `rtl_comrade v<x>` (or rtl_buddy parity) banner. Not catalogued. |
| 5 | `show_git_rev()` print + log | — | Missing | Not in catalog or specs. Plan B does not reproduce the git status line that rtl_buddy emits for the test command. |
| 6 | Discover `root_config.yaml` | `discover-config-file` | Full | `03-module-catalog.md` L24-L31; spec 04 L13-L17. |
| 7 | Parse root config | `parse-root-config` | Full | Catalog L33-L37; schema in spec 01 L17-L23. |
| 8 | Eager `RegConfig` init | — | Out-of-scope-by-design | Reg-cfg loading is a regression-graph concern (08-sibling-graphs.md). In `test`, dropping it is harmless because nothing reads it. |
| 9 | uname + platform match | `select-platform` | Full | Catalog L39-L45. |
| 10 | Builder resolution from platform | `resolve-builder` | Full | Catalog L46-L52; honours `--builder` override. |
| 11 | `--builder` callback validation | `resolve-builder` (critical-log on unknown) | Partial | Spec 04 L24 calls for critical-log on unknown override, but rtl_buddy does this *before* the command runs via Typer `callback`. Plan B handles it as a post-CLI critical instead. Behavioural close but UX-different (the error surfaces deeper). |
| 12 | Verible cfg init | — | Out-of-scope-by-design | The `test` command does not exercise verible; safe to skip. Plan B's schema spec 01 still has VeribleConfig types so root-config parses. |
| 13 | Default builder-mode `"debug"` | CLI edge default `"debug"` on `cc-build`/`sim-build` | Full | 06-graph-yaml.md L121-L122. |
| 14 | RunDepth / early-stop globals | `early-stop-gate` instances + CLI edge `early_stop` default `"post"` | Full | Catalog L289-L295; spec 10 L15-L19. Phase ordering implementation flagged 07 impl note. |
| 15 | Suite config load | `parse-suite-config` | Full | Catalog L53-L60; spec 04 L24-L26. |
| 16 | `--list` branch | `route-list-mode` + `list-test-names` | Full | Catalog L72-L83. Note: rtl_buddy prints names with two-space separator (`"  ".join(...)`); spec 05 L17-L19 says the same. |
| 17 | SeedMode derivation | `derive-seed-mode` | Full | Catalog L61-L65. Spec 04 L28-L30 confirms the precedence: `rnd_new` wins, then `rnd_last → REPLAY`, else `DEFAULT`. |
| 18 | `run_ids=[None]` default | `expand-runs` default param `run_ids=[None]` | Full | Catalog L199-L204; 06 L194 notes "unwired for plain test." |
| 19 | Select test by name / all | `select-tests` | Full | Catalog L85-L97. |
| 20 | Reglvl filter + Skip rows | `filter-reglvl` | Full (test) | Catalog L99-L106. For plain `test`, both inputs unwired → keep-all (07 verify 21 calls out the validation risk). |
| 21 | get_reglvl branching | inside `filter-reglvl` | Partial | Spec 01/spec 05 do not explicitly call out the four-case match (int/dict-with-builder/dict-with-default/None/critical-on-malformed); plan assumes the schema's `TestConfig.get_reglvl` method ports verbatim. Should be explicit. |
| 22 | Sweep expansion `exec` | `expand-sweep` | Full | Catalog L115-L121; spec 05 L25-L31. |
| 23 | Per-test TestRunner instantiation | (graph topology — no single module) | Full | The graph is the runner; correlated via `keyed_join`. |
| 24 | one-shot vs run_multiple | `expand-runs` collapses both into a fan-out generator | Full | Catalog L199-L204; 04 pipeline-and-contracts. |
| 25 | Lazy/eager model load | `load-model` (lazy after filter) | Full (divergent) | Catalog L107-L114. 07 settled 8 notes this is an intentional divergence — broken models on skipped tests no longer raise. |
| 26 | Create `logs/` dir | — | Missing | No module spec creates `logs/`. `build-compile-cmd` and `build-sim-cmd` are described as computing `logs/<test>.compile.log/.err` paths but no spec mentions `os.makedirs(logs/, exist_ok=True)`. `run-process` will fail with FileNotFoundError on first compile if `logs/` does not pre-exist. |
| 27 | Build-tag/dir/simv resolution | `build-compile-cmd` (folds `build_dir`+`simv` into ctx) | Full | Catalog L146-L155; spec 07 L15-L26. |
| 28 | Preproc `exec` | `run-preproc` | Full | Catalog L126-L130; spec 06 L13-L17. |
| 29 | Early-stop at pre | `early-stop-gate` instance `gate-pre` | Full | 04 pipeline L22, 05 L13. |
| 30 | Write `run.f` filelist | `write-filelist` | Full | Catalog L132-L141; spec 06 L17-L24. Filename collision under concurrency is flagged (07 KIV 17). |
| 31 | Filelist parsing rules (regex, `-F` recursion, `+incdir+`/`+libext+`, env expansion, existence checks, `-f`→critical) | `write-filelist` (reimplemented) | Partial | Spec 06 L42-L46 says "port carefully" but acceptance only specifies "byte-for-byte modulo ordering"; no separate sub-spec enumerates the regex/recursion/`+libext+` consolidation/`-f` critical behaviour. Implementer is expected to read rtl_buddy source. |
| 32 | Compile argv | `build-compile-cmd` | Full | Spec 07 L15-L23. |
| 33 | Plusdefines/plusargs formatting | `build-compile-cmd`, `build-sim-cmd` | Full | Spec 07/08 reference `VlogSim.compile`/`execute` argv. Implementation must replicate the `+name` vs `+name=val` distinction. |
| 34 | Compile subprocess + dumps | `run-process` (compile instance) | Partial | `run-process` redirects to files (settled 12). It deliberately does *not* re-log stdout/stderr at error level the way `VlogSim.compile` does (lines 169-174 of vlog_sim.py). Spec 07 L26 says `interpret-compile` "reads `proc[stderr_path]/stdout_path` and logs at ERROR" — that covers the ERROR dump on fail, but skips the time-spinner (concern 54) and the `FileNotFoundError` critical for missing builder exe (concern 34 sub). |
| 35 | Compile-fail short-circuit | `interpret-compile` `fail` port | Full | Catalog L185-L194; spec 07 L24-L26. |
| 36 | Early-stop at comp | `early-stop-gate` `gate-comp` | Full | 04 pipeline L26-L27. |
| 37 | run-multiple/run-id loop with replay_run_id fallback (REPLAY+`replay_run_id is None` → uses current run_id) | `expand-runs` + `resolve-seed` | Partial | Catalog L199-L216 expects `resolve-seed` to do REPLAY with `ctx["run_id"]`. Spec 08 L23 confirms "uses `ctx["run_id"]` for the suffix." The original rtl_buddy fallback semantics (REPLAY mode but `replay_run_id` is None at the suite level → falls back to current run_id, `test_runner.py:L106-L108`) is implicitly captured by emitting `run_ids=[None]` for plain `test`. For `randtest` (out of scope here), this is correctly handled in 08-sibling-graphs.md. For plain `test`, `replay_run_id` is always `None`, so this is fine. |
| 38 | Seed resolution (NEW/DEFAULT/REPLAY) | `resolve-seed` | Full | Catalog L210-L217; spec 08 L18-L27. |
| 39 | Replay-missing-seed FAIL stub (.log/.err + symlinks + rc=1) | `resolve-seed` | Partial | Spec 08 L23-L27 explicitly flags this as uncertain: "on missing/invalid file, emit a `result` envelope with `SimTimeoutResults`-style FAIL? — actually per [03] writes a FAIL stub log + symlinks (verify against rtl_buddy `VlogSim.execute` REPLAY-missing path)." The module sketch in catalog L210-L216 does not describe this branch at all. Behaviour is unresolved. |
| 40 | Sim argv | `build-sim-cmd` | Full | Catalog L218-L226. |
| 41 | Per-test timeout via `test.get_timeout()` + custom-warn | `build-sim-cmd` emits `("timeout", float | None)` | Partial | Spec 08 L29-L32 mentions timeout pulled from test config but does not mention the `logger.warn(... custom sim_timeout ...)` line that rtl_buddy emits on a custom timeout (`vlog_sim.py:L233-L234`). Cosmetic but observable in logs. |
| 42 | Sim subprocess (redirect, setpgrp, SIGINT→SIGQUIT, timeout, rc=4444) | `run-process` | Partial | Catalog L156-L179 sketches `setpgrp`+SIGQUIT+`rc=4444` but does *not* sketch the SIGINT (Ctrl-C) handler that rtl_buddy installs (`vlog_sim.py:L246-L249`). Spec 03 L33-L34 acceptance includes "SIGINT … cancels the subprocess cleanly without leaving zombies", so it's planned for, but the catalog sketch omits it. |
| 43 | `.randseed` write + HierInstanceSeed append | `write-randseed` | Full | Catalog L235-L242; spec 08 L33-L36. |
| 44 | `test.log/.err/.randseed` symlink forcing | `link-latest` | Full | Catalog L243-L249. |
| 45 | Sim-timeout terminal | `interpret-sim` (via `ctx["timed_out"]`) | Full | Catalog L251-L256; spec 08 L37-L39. |
| 46 | Early-stop at sim | `early-stop-gate` `gate-sim` | Full | 04 pipeline L34-L35. |
| 47 | uvm vs plain post dispatch | `route-post` | Full | Catalog L262-L268. |
| 48 | VlogPost log scan | `parse-log` | Full | Catalog L270-L276; PASS-wins-over-FAIL quirk explicitly inherited (07 open 15). |
| 49 | UvmVlogPost severity parse | `parse-uvm-log` | Full | Catalog L278-L283. |
| 50 | Aggregate summary print | `aggregate-results.finalise()` | Partial | Spec 10 L17-L20 says it "prints the summary table (key/test_name, result, desc)" but the table-format alignment (`<30`, `<8`, `<30` columns) of rtl_buddy is not specified, and `logger.result(...)` (the custom RESULT log level) doesn't exist in rtl_comrade. Plan B uses standard `log.info` per the catalog snippet. Functional but formatting parity is loose. |
| 51 | OR-accumulated exit code | `aggregate-results.finalise()` → `log.error` → harness exit 1 | Full | 05 L101-L110; 07 settled 10. |
| 52 | `typer.Exit(exit_code)` | harness exit mechanism | Full | Via logging→exit invariant. |
| 53 | `\r` cleanup after sim spinner | — | Missing | No module is responsible for the `print(" "*80, end='\r', …)` cleanup line rtl_buddy emits in `do_cmd_test` and inside `vlog_sim`. Cosmetic. |
| 54 | Compile/sim elapsed-time spinner lines | — | Missing | rtl_buddy's "test X vlog compile time N secs\r" / "vlog run time N secs\r" lines are user-facing progress feedback. `run-process` is silent about timing. No spec mentions reproducing them. Cosmetic but a UX regression. |

## Section C — Atomicity assessment

Catalog reference: `03-module-catalog.md`.

| # | Module | Atomicity | Notes |
|---|---|---|---|
| 1 | `discover-config-file` (L24-L31) | Atomic | Single concern: walk up tree, emit Path. Generic and reusable. |
| 2 | `parse-root-config` (L33-L37) | Atomic | Pure YAML deserialise. |
| 3 | `select-platform` (L39-L44) | Atomic | One subprocess + one match. |
| 4 | `resolve-builder` (L46-L51) | Atomic | One lookup + override application. Critical-log on unknown override is data, not scheduling. |
| 5 | `parse-suite-config` (L53-L59) | Atomic | One file → one suite_cfg, including testbench bind and suite-dir capture. The testbench bind is local to the same file so this stays atomic. |
| 6 | `derive-seed-mode` (L61-L65) | Atomic | Two bool inputs → one enum. Trivial and warranted (notes already discuss whether to absorb into `resolve-seed`, 07 KIV 18). |
| 7 | `route-list-mode` (L72-L76) | Atomic | Pure named-port classifier. |
| 8 | `list-test-names` (L78-L83) | Atomic | Terminal print sink. |
| 9 | `select-tests` (L85-L96) | Atomic | Generator over `suite_cfg.get_tests(name)`; one concern. |
| 10 | `filter-reglvl` (L99-L106) | Atomic | Single reglvl-window check with named-port routing. Builder enters as persistent config. |
| 11 | `load-model` (L107-L114) | Atomic | One file load, one attach to ctx. Lazy split from suite parse is intentional (07 settled 8). |
| 12 | `expand-sweep` (L115-L121) | Atomic | Generator; the `exec`'d script is data the module runs, not scheduling. |
| 13 | `run-preproc` (L126-L130) | Atomic | Same shape as sweep; exec mutates test and emits ctx unchanged. |
| 14 | `write-filelist` (L132-L141) | Atomic | One file write, two-port emit (ctx + filelist) for lockstep downstream pairing. The size of the underlying reimplementation (regex, `-F` recursion, `+libext+`/`+incdir+`, dedup, existence checks per `vlog_filelist.py:L26-L135`) is *internal* to one piece of node-local work — the file the node writes — so it remains atomic by the rtl_comrade definition. |
| 15 | `build-compile-cmd` (L146-L154) | **Composite (justified)** | Does three things: assemble argv, derive `build_dir`/`simv` (depends on verilator vs other), and compute log paths. The triple is tightly coupled — they all derive from `(builder_cfg, builder_mode, test)` and folding `simv` into ctx is what removes `keyed_join`'s need for a config port (07 impl note). Splitting would force a second join. Keep. |
| 16 | `run-process` (L156-L183) | Atomic | The reusable subprocess primitive: argv → rc/timed_out + paths. Single concern. The fact that it is used at two graph positions is reuse, not composite-ness. |
| 17 | `interpret-compile` (L185-L194) | Atomic | One rc check, named-port routing on the joined inputs. The keyed_join is the *contract*, not the module. |
| 18 | `expand-runs` (L199-L204) | Atomic | Generator over run_ids. |
| 19 | `resolve-seed` (L210-L216) | **Composite (should split)** | Branches into three modes (`NEW`/`DEFAULT`/`REPLAY`) and also (per spec 08 L23-L27) needs to handle REPLAY-missing-seed by writing a FAIL stub log, two stub files, two symlinks, and emitting a terminal result. That is two different concerns: (a) compute or load a seed; (b) emit a FAIL-stub + terminal for the missing-replay case. Suggested split: a `seed-resolve` module emitting `("seed", …)` on success and `("replay_missing", result)` as a terminal port, with the FAIL-stub writes (the stub `.log`/`.err` + symlink force) delegated to existing infrastructure or a tiny `write-fail-stub` module. As designed, spec 08 even flags this as unresolved ("verify against rtl_buddy"). |
| 20 | `build-sim-cmd` (L218-L226) | **Composite (justified)** | Same pattern as `build-compile-cmd`: assembles argv, computes timeout, computes log paths, folds `seed`+`log` into ctx, emits three named outputs. The triple is tightly coupled to `(builder_cfg, builder_mode, test, seed)` and the lockstep with `run-process` requires emitting `command`+`timeout` together. Keep. |
| 21 | `write-randseed` (L235-L242) | Atomic | Single file write (with optional HierInstanceSeed append). The keyed_join is the contract. |
| 22 | `link-latest` (L243-L249) | Atomic | Three force-symlinks in CWD, all from the same ctx. |
| 23 | `interpret-sim` (L251-L256) | Atomic | Pure routing on `ctx["timed_out"]`. |
| 24 | `route-post` (L262-L268) | Atomic | Pure named-port classifier on `ctx["test"].uvm`. |
| 25 | `parse-log` (L270-L276) | Atomic | One file scan, one TestResults. |
| 26 | `parse-uvm-log` (L278-L283) | Atomic | One file scan, one TestResults. |
| 27 | `early-stop-gate` (L289-L295) | Atomic | Pure phase comparison + routing. Three instances differ only by `config.phase`, which is data, not scheduling. |
| 28 | `aggregate-results` (L297-L322) | Atomic (with `finalise()`) | `run()` appends; `finalise()` summarises + logs. Both are local to the node. The `merge` contract carries the scheduling. |

**Scheduling-in-modules audit:** No module in the catalog contains scheduling. Every branching point (`route-list-mode`, `filter-reglvl`, `interpret-compile`, `interpret-sim`, `route-post`, `early-stop-gate`) is a *data classifier* expressed as a named-port return — explicitly allowed by `docs/modules/implementation.md:L323-L332`. Pacing/correlation/fan-in is in `default` + `keyed_join` + `merge` contracts. This is the cleanest part of the plan.

## Section D — Gap list (prioritised)

### Functional gaps (severity high → medium)

1. **`logs/` directory creation is unowned.** rtl_buddy's `VlogSim.__init__` makes `logs/` (`vlog_sim.py:L55-L59`). Plan B writes there from at least three modules (`build-compile-cmd` log paths, `run-process` redirect, `write-randseed`, `link-latest`) without specifying who creates it. First compile will fail with FileNotFoundError. Assign creation to either a setup module or `run-process` (`exist_ok=True`).
2. **REPLAY-missing-seed FAIL path is unresolved.** Spec 08 L23-L27 explicitly flags uncertainty around how `resolve-seed` should reproduce `vlog_sim.py:L200-L212` (write `FAIL replay seed missing` to `.log`, write `.err`, force-symlink `test.log`/`test.err`, return `rc=1`). Decide and put it in spec 08; consider a dedicated `replay_missing` terminal port to keep `resolve-seed` atomic.
3. **`.` prepended to `PATH` is unassigned.** 01-cli-and-entry.md L50-L52 and 07 implementation notes acknowledge the obligation, but no module spec owns it. Without this, CWD-local `simv`/`verilator` discovery breaks. Pick one: `resolve-builder` (one-time setup), `run-process` (every invocation), or a tiny `prepare-env` setup node.
4. **Compile-stage `FileNotFoundError` for a missing builder exe** is critical-logged by rtl_buddy (`vlog_sim.py:L164-L165`). Plan B's `run-process` sketch (catalog L167-L179) does not handle the `FileNotFoundError` from `asyncio.create_subprocess_exec`. Spec 03 acceptance criteria don't mention it. Specify whether this should critical-log (rtl_buddy parity) or emit a normal `proc{rc=…}`.
5. **`get_reglvl` error handling not specified.** rtl_buddy critical-logs on malformed reglvl entry (`config/test.py:L296-L297`). Plan B's schema spec 01 says "runtime `TestConfig` with `get_reglvl(builder)`" but spec 05 doesn't enumerate the four-case branch (int / dict-with-builder / dict-with-default / None / malformed-critical).
6. **Test-name not-found behaviour.** rtl_buddy critical-logs (`config/suite.py:L62-L64`) which aborts the run. Plan B's spec 05 mentions "unknown name critical-logs" in tests but neither `select-tests` catalog nor its sketch (catalog L92-L97) shows the critical branch. Make explicit.
7. **Startup version banner missing.** rtl_buddy's `logger.info(f'rtl_buddy v{version(...)}')` (`rtl_buddy.py:L152`) has no Plan B analogue. Minor but observable; either drop deliberately and document, or add a startup banner.
8. **`show_git_rev()` not reproduced.** rtl_buddy prints branch/commit/mod/staged for test commands (`rtl_buddy.py:L500-L522`). Not in the catalog. Either explicitly drop (with a note) or assign to a setup node.

### Atomicity / structural issues (medium)

9. **`resolve-seed` should split** (Section C item 19). The current single-module design handles three seed-mode branches *and* a terminal failure-path with side-effecting stub-file writes and symlink force. Suggested split: `resolve-seed` emits `("seed", …)` or `("replay_missing", result)`; the existing `link-latest`/file-stub work moves to a small reusable `write-fail-stub` (or merges with `link-latest`'s symlink mechanism since the rtl_buddy code path force-symlinks the stub paths too).
10. **`build-compile-cmd` carries `build_dir` derivation though `cc-int` never reads it.** The `simv` path is needed at `cc-int` (so folding into ctx makes sense), but `build_dir` is only needed by the compile invocation itself (verilator `--Mdir`). It could live entirely inside `build-compile-cmd` without entering ctx. Minor; not worth resisting since the catalog already says "folds `build_dir`/`simv` into ctx". Verify nothing downstream reads `build_dir`.

### Cosmetic / parity gaps (low)

11. **Sim-time-spinner output dropped.** `print("test %s vlog compile time %d secs\r" % …)` and similar in rtl_buddy (`vlog_sim.py:L178, L276`). Plan B is silent. Either reproduce in `run-process` (or a tiny `report-elapsed` finalise hook) or document the UX drop.
12. **`\r`-cleanup line after sim** (`rtl_buddy.py:L368`). Same as above.
13. **`logger.warn` on custom sim_timeout** (`vlog_sim.py:L233-L234`). Spec 08 mentions timeout pulled from config but not the warn line.
14. **Summary table formatting** (`<30`/`<8`/`<30` columns + `logger.result`). Plan B's catalog snippet (L307-L322) uses `log.info` and structured keys, losing the rtl_buddy table look. Either preserve column layout or document as intentional drop. (07 settled 11 explains the logging philosophy but doesn't address summary format.)
15. **`PassFailFormatter` color codes for PASS/FAIL/NA** (`rtl_buddy.py:L39-L60`). 07 settled 11 explicitly drops `--color`; document as accepted UX change.
16. **`logger.error` dumps of stdout/stderr on compile fail** (`vlog_sim.py:L169-L171`). Spec 07 L26 covers this for `interpret-compile`. Verify spec implementer uses ERROR-level (which the harness maps to exit 1) and not INFO/WARNING.

### Validation/risk items already flagged by Plan B (no action needed beyond what 07 already says)

17. 07 verify items 19/20/21/22/23 are real probes (spec 00). These are not gaps in the plan, just framework-empirical risks the plan acknowledges.

## Section E — Summary

Plan B covers the rtl_buddy `test` flow well in its **structural** decomposition: roughly 39 of the 54 concerns map to a clearly-named atomic module with a sensible contract pairing, and 8 more are explicitly out-of-scope-by-design (regression-only items, `--debug`/`--color`/logger setup that the harness owns). The 27-module catalog is impressively atomic — every branching point is a named-port classifier rather than scheduling, the only `keyed_join`s are at the two genuine fast-meets-slow merges (`cc-int`, `randseed`), the bespoke `merge` contract correctly handles mutually-exclusive terminal fan-in into `aggregate-results`, and the `run-process` reuse for compile/sim is the right primitive.

The plan's atomicity by rtl_comrade's definition is strong overall: 25 of 27 modules are atomic, 2 are composites I'd justify (`build-compile-cmd`, `build-sim-cmd` — the lockstep emission of `ctx`+`command`(+`timeout`) is structurally necessary to avoid spurious joins), and only one module (`resolve-seed`) genuinely warrants a split, mostly because spec 08 itself admits the REPLAY-missing branch is unresolved.

The biggest weakness is **missing operational glue**: `logs/` directory creation, `.`-on-`PATH`, builder-exe `FileNotFoundError` handling, REPLAY-missing seed FAIL stub semantics, and `select-tests`/`get_reglvl` critical-log paths are all referenced obliquely or in 07 implementation notes but never get an explicit module owner or spec deliverable. None is hard to fix — most are one-line additions to existing modules — but absent a clear owner the implementer will discover them at integration time. Closing gaps 1–6 from Section D before starting implementation would substantially de-risk the build. Cosmetic parity (spinner output, color, summary formatting, banner, git-rev print) is intentionally relaxed and is acceptable provided the divergences are documented; 07's "Notable divergences" list should be extended to cover them.
