# Audit: Plan A (`test-implementation/`) vs rtl_buddy `test` command

## Section A — Reference-flow concern inventory

Citations refer to files under `rtl_buddy/src/rtl_buddy/`.

1. **Typer app construction & command dispatch** for `test` — `rtl_buddy.py:L88-L107`.
2. **Prepend `.` to `PATH`** so locally-built simv is invokable without `./` prefix — `rtl_buddy.py:L101-L102`.
3. **`--version` callback** exiting before any other work — `rtl_buddy.py:L83-L87,L122`.
4. **Custom `RESULT` logging level** (`25`) and `Logger.result` injection — `rtl_buddy.py:L25-L29,L126-L128`.
5. **Console + file handlers**: `ExitHandler` to console (DEBUG if `--debug` else `RESULT`), `rtl_buddy.log` file handler (INFO/DEBUG) — `rtl_buddy.py:L135-L149`.
6. **`PassFailFormatter`** ANSI colour highlighting of `PASS/FAIL/NA` (gated by `--color`) — `rtl_buddy.py:L39-L60,L143-L146`.
7. **`CRITICAL` → immediate `typer.Abort()`** via `ExitHandler.emit` — `rtl_buddy.py:L32-L36`.
8. **rtl_buddy version banner log** at start of every command — `rtl_buddy.py:L152`.
9. **Git status print** for `test/randtest/regression/filelist`, **suppressed under `test --list`** — `rtl_buddy.py:L109-L154,L500-L522`.
10. **`builder_override` validation callback** (must be a configured builder name) — `rtl_buddy.py:L70-L81`.
11. **`RootConfig` discovery** — walks upward from cwd up to 8 levels for `root_config.yaml`; fatal if not found — `config/root.py:L16-L36`.
12. **Root config YAML load + serde deserialization** with `RootConfigFile` schema — `config/root.py:L83-L91`.
13. **Builder & verible registries** populated from root config — `config/root.py:L93-L97`.
14. **Regression config (`reg_cfg`) initialised** from `cfg-rtl-reg.path` (used by `regression`, but `RootConfig.__init__` always builds it for `test` too) — `config/root.py:L99-L104`.
15. **Platform selection by `uname`** with fatal if no platform matches — `config/root.py:L106-L120`.
16. **Builder selection** within platform, honouring `builder_override` — `config/root.py:L115,platform.py via initialise`.
17. **Effective `rtl_builder_mode` defaulting**: `test` defaults to `"debug"` when unset — `rtl_buddy.py:L178`.
18. **`run_depth` plumbed from root option** (`-E/--early-stop`) defaulting to `POST` — `rtl_buddy.py:L121,L160`.
19. **Suite config (`tests.yaml`) load** with serde, builds testbench lookup and per-test envelopes (resolves `model_path` relative to suite dir) — `config/suite.py:L26-L51`, `config/test.py:L320-L323`.
20. **Fatal on missing/malformed testbench** referenced by a test — `config/suite.py:L41-L49`.
21. **`--list` short-circuit**: print `"  ".join(test_names)` then `typer.Exit(0)` — `rtl_buddy.py:L182-L184`.
22. **Single test name lookup**; fatal when name is not in suite — `config/suite.py:L52-L67`.
23. **Default `run_ids = [None]`** for plain `test` — `rtl_buddy.py:L188`.
24. **Seed-mode selection from `--rnd-new/--rnd-last`** with `rnd_new > rnd_last > default` priority — `rtl_buddy.py:L189-L194`.
25. **Per-test iteration in `_do_test_suite`** with regression-level bounds (left unset by `test`) — `rtl_buddy.py:L346-L367`.
26. **Builder-aware `reglvl` resolution** (`int` | `dict` w/ builder + default | `None→0`); fatal on malformed — `config/test.py:L266-L299`.
27. **Skip-bounds gating**: `t_lvl > reg_level` or `t_lvl < start_level` produces SKIP, **one row per `run_id`** — `rtl_buddy.py:L259-L262,L350-L357`.
28. **Sweep expansion** (`sweep.path` exec-d with `logger`, `TestConfig`, `test_cfg`, `root_cfg`, `out_test_cfgs`); `critical` on script exception; passthrough when `sweep_path is None` — `rtl_buddy.py:L264-L283,L360`.
29. **`TestRunner` instantiation once per expanded test** with single-or-multi-run branching — `rtl_buddy.py:L285-L299`, `runner/test_runner.py:L22-L36`.
30. **`VlogSim` construction**: derives `output_dir = "logs"` (mkdir), `build_tag` (safe regex), `build_dir = obj_dir_<tag>`, `testbench` — `tools/vlog_sim.py:L38-L86`.
31. **Preproc hook** (per expanded test, before PRE gate): exec script with `logger`, `test_cfg`, `root_cfg`; `critical` on exception; logs "No preproc script" otherwise — `tools/vlog_sim.py:L119-L139`, `runner/test_runner.py:L57`.
32. **Early-stop at PRE** returns `EarlyStopResults("Stopped early at preproc")` — `runner/test_runner.py:L59-L60,L94-L95`.
33. **Filelist generation (`run.f`)** with `unroll=True, flatten=False, strip=False, deduplicate=True`, embedding model + testbench filelist — `tools/vlog_sim.py:L88-L93`, `tools/vlog_filelist.py:L137-L159`.
34. **Filelist `-F` recursion**, **`-f` rejection (fatal)**, **`+libext+` consolidation**, **`+incdir+` dir check**, **source file-existence check (error)** — `tools/vlog_filelist.py:L26-L135`.
35. **Compile command construction**: `[exe] + compile_time_opts(mode) + [--Mdir <build_dir>] (verilator only) + plusdefines + ["-f","run.f"]` — `tools/vlog_sim.py:L141-L160`.
36. **Compile execute (subprocess.run, capture_output=True)**; `FileNotFoundError` → critical; error-level dump of stdout+stderr on non-zero; debug-dump on zero; transient `\r` print of duration — `tools/vlog_sim.py:L161-L179`.
37. **Compile failure → `CompileFailResults`**, **one per `run_id`** (multi-run path duplicates) — `runner/test_runner.py:L63-L66,L97-L99`, `runner/test_results.py:L44-L51`.
38. **Early-stop at COMP** returns `EarlyStopResults("Stopped early at compile")` — `runner/test_runner.py:L67-L68,L101-L102`.
39. **Run-id loop in multi-run**: pre+compile once, sim/post per run-id; replay defaults `replay_run_id` to current `run_id` when unspecified — `runner/test_runner.py:L82-L117`.
40. **Seed resolution**: `replay` reads `<output_dir>/<test_name>[_NNNN].randseed` (`logs/...`), `new` uses `random.randrange(1_000_000)`, `default` uses `rtl_builder_cfg.get_seed()` — `tools/vlog_sim.py:L181-L220`.
41. **Replay seed missing/invalid path**: writes compatibility `.log` + `.err` evidence, force-symlinks `test.err`/`test.log`, returns `1` (not 4444) — `tools/vlog_sim.py:L197-L213`.
42. **Sim command runtime construction**: `[simv_path] + run_time_opts(mode, seed=) + plusdefines + plusargs` (plusargs supports value/no-value) — `tools/vlog_sim.py:L95-L106,L222-L228`.
43. **Custom-timeout warning log** when `test_cfg.timeout` is set — `tools/vlog_sim.py:L232-L234`, `config/test.py:L210-L219`.
44. **Log path convention**: `logs/<test_name>[_NNNN]` with `.log`/`.err`/`.randseed` siblings — `tools/vlog_sim.py:L82-L86,L240-L274`.
45. **Sim subprocess with `os.setpgrp` + SIGINT→SIGQUIT handler** for graceful Ctrl-C; timeout falls through to send SIGQUIT, returns sentinel `4444` — `tools/vlog_sim.py:L240-L262`.
46. **Randseed file write** (always, after sim attempt); appends `HierInstanceSeed.txt` contents when `hier_inst_seed` appeared in argv — `tools/vlog_sim.py:L263-L269`.
47. **`force_symlink` to `test.err`, `test.log`, `test.randseed`** (in cwd) — `tools/vlog_sim.py:L26-L31,L271-L273`.
48. **Sim timeout → `SimTimeoutResults("Sim hit timeout")`**; non-timeout non-zero return code still proceeds to post — `runner/test_runner.py:L72-L73,L110-L111`, `runner/test_results.py:L62-L69`.
49. **Early-stop at SIM** returns `EarlyStopResults("Stopped early at sim")` — `runner/test_runner.py:L75-L76,L112-L113`.
50. **Post parser selection**: `UvmVlogPost` iff `test_cfg.uvm` truthy else `VlogPost` — `tools/vlog_sim.py:L287-L300`.
51. **Default log parser**: scans for `^PASS`, `^FAIL`, `^(ERR|FAT):`; PASS overrides FAIL via assignment order; default `result="NA", desc="test result unknown"` — `tools/vlog_post.py:L23-L45`.
52. **UVM parser**: regex over `UVM Report Summary` header + counts (`INFO/WARNING/ERROR/FATAL`); fails on missing block or missing keys; PASS iff `WARNING≤max_warns ∧ ERROR≤max_errors ∧ FATAL==0` — `tools/vlog_post.py:L48-L81`, `tools/vlog_sim.py:L292-L298`.
53. **`TestResults` default-shape normalisation** (missing `result`→`NA`, missing `desc`→`NA`) — `runner/test_results.py:L15-L27`.
54. **`is_pass()` semantics**: `PASS` and `SKIP` are pass-like, all others fail — `runner/test_results.py:L29-L30`.
55. **Summary string accumulation per row** with `test_name<30`, `result<8`, `desc<30` column widths plus trailing newline — `rtl_buddy.py:L203-L207`.
56. **Exit code accumulation**: `exit_code |= 0 if results.is_pass() else 1`, raised via `typer.Exit(exit_code)` — `rtl_buddy.py:L196,L206,L209`.
57. **`\r`-blanking print** to clear transient sim/compile status line before final summary — `rtl_buddy.py:L368`, `tools/vlog_sim.py:L178,L276`.
58. **Result row shape** `{'test_name', 'randmode_i', 'results'}` (one entry per run id, including skipped) — `rtl_buddy.py:L259-L262,L301-L303`.

## Section B — Module-to-concern coverage table

| # | rtl_buddy concern | Plan A module(s) | Rating | Notes |
|---|---|---|---|---|
| 1 | Typer command registration | (none — harness graph runner CLI) | Out-of-scope-by-design | rtl-comrade harness provides the CLI; not a module concern. |
| 2 | PATH `.` prepend | (none) | Missing | No spec adds `.` to `PATH`; locally-built simv will fail to exec from cwd. |
| 3 | `--version` short-circuit | (none) | Out-of-scope-by-design | Owned by harness. |
| 4 | Custom `RESULT` log level | (none) | Missing | Spec 20 relies on harness-level logging only; the `RESULT` (25) channel for `result_string` is not reproduced. |
| 5 | Console/file handler split + colour | (none) | Out-of-scope-by-design | Plan A defers to harness logging. |
| 6 | `PassFailFormatter` ANSI | (none) | Missing | `--color` CLI flag is plumbed (`TestCliArgs.color`) but no module renders coloured PASS/FAIL/NA. |
| 7 | `CRITICAL`→Abort | harness invariant | Full | rtl-comrade invariants doc says CRITICAL is immediate `SystemExit(1)`. |
| 8 | Version banner | (none) | Missing | No spec emits version log. |
| 9 | Git status (suppressed on `--list`) | `GitStatusReport` (spec 22) | Partial | Spec 22 is optional/last; doesn't gate on `list_tests`. Master plan §6.3 mentions `test --list` suppression but spec 22 omits it. |
| 10 | `builder_override` validation callback | `RootBootstrap` (spec 03) | Partial | Spec 03 only fatal-errors if chosen builder is absent; no upfront validation against discovered builder names (no equivalent of `cb_builder`). |
| 11 | `root_config.yaml` discovery (walk up) | `RootBootstrap` (spec 03) | Full | Spec 03 step 1 ports `_discover_root_cfg`. |
| 12 | Root config YAML load | `RootBootstrap` (spec 03) | Partial | Spec 03 hand-rolls YAML loading rather than reusing the serde `RootConfigFile` schema (`rtl-buddy-filetype: project_root_config`, `cfg-rtl-builder`, `cfg-platforms`, `cfg-rtl-reg`, `cfg-verible`). Top-level keys assumed in spec 03 (`platform`, `builder`) do not match rtl_buddy's actual keys (`cfg-platforms`, `cfg-rtl-builder`). |
| 13 | Builder/Verible registries | `RootBootstrap` | Partial | `rtl_builder_cfg` dict for selected builder is carried; verible registry omitted (acceptable for `test`, but the `cfg-verible` field still needs to deserialize cleanly). |
| 14 | Reg-config initialisation | (none) | Out-of-scope-by-design | `test` command doesn't use `reg_cfg`; safe to omit. |
| 15 | Platform selection by `uname` | `RootBootstrap` | Partial | Spec 03 uses `platform.uname().system.lower()` mapping but rtl_buddy compares exact `uname` stdout (e.g. `"Linux"`/`"Darwin"`) against `cfg-platforms[i].get_unames()`. Subtle case/value mismatch. |
| 16 | Builder selection w/ override | `RootBootstrap` | Full | Spec 03 step 4. |
| 17 | Default `rtl_builder_mode="debug"` | `RootBootstrap` | Full | Spec 03 step 5. |
| 18 | `run_depth` plumbing | `RootBootstrap` | Full | Carried in `RootContext.run_depth`. |
| 19 | Suite config load + envelope build | `SuiteConfigLoad` (spec 04) | Partial | Top-level YAML keys assumed `testbenches` (dict) and `tests` (list); rtl_buddy uses `testbenches: list[TestbenchConfig]` and serde-required `rtl-buddy-filetype: test_config` discriminator. Schema mismatch. |
| 20 | Fatal on bad testbench | `SuiteConfigLoad` | Full | Spec 04 step 4b says fatal. |
| 21 | `--list` short-circuit | `ListTestsBranch` + `ListTestsRender` (spec 05) | Full | Two-node split routes around test execution and renders. |
| 22 | Single-test lookup, fatal on miss | `TestSelect` (spec 05) | Full | Spec 05 step 1. |
| 23 | `run_ids = [None]` for plain test | `RunIdPlan` (spec 08) | Full | Spec 08 step 1. |
| 24 | Seed mode flag priority | `SeedModeSelect` (spec 02) | Full | Spec 02 ordering matches rtl_buddy. |
| 25 | Iterate per-test + reg bounds | `TestSelect` + `RegressionLevelSkipFilter` (specs 05, 06) | Full | Generator emits per-test; filter applies bounds. |
| 26 | Builder-aware `reglvl` | `RegressionLevelSkipFilter` (spec 06) | Partial | Spec 06 handles `int`, `dict`, `None`, but falls back to `0` on missing builder key; rtl_buddy uses `default` key then critical. Behaviour drift on malformed config. |
| 27 | Skip → one row per `run_id` | `RegressionLevelSkipFilter` (spec 06) | **Missing** | Spec 06 emits **one** skip row per test, not one per run id; the `run_ids` input listed in master plan §6.9 is dropped in the actual module spec. Functional cardinality drift for future randtest reuse; plain `test` still works because run_ids=[None]. |
| 28 | Sweep expansion w/ namespace | `LegacySweepExpand` (spec 07) | Partial | Namespace includes `logger`, `TestConfig`, `test_cfg`, `root_cfg`, `out_test_cfgs`. But: `TestConfig` is bound to `TestConfigEnvelope`, not the rtl_buddy class — legacy sweep scripts that construct `TestConfig(...)` with rtl_buddy's positional signature will break. Also `root_cfg` is `RootContext` not `RootConfig`. Compatibility risk for existing user scripts. |
| 29 | TestRunner per expanded test | (decomposed across pipeline) | Full | Decomposition is the whole point. |
| 30 | VlogSim construction (logs/, build_tag, build_dir) | `FilelistGenerate`/`SimCommandBuild` | Partial | Spec 11 step 1-2 reproduces `safe_name` and `build_dir` but **does not preserve `logs/` `output_dir`** convention. Spec 15 puts log paths under `build_dir`, not `logs/<test_name>`. Path-shape regression. |
| 31 | Preproc hook (per expanded test) | `LegacyPreproc` (spec 09) | Partial | Per-expanded-test cardinality is intended, but in the graph `LegacyPreproc` sits downstream of `RunIdPlan`, so it actually runs **per run id**. For plain `test` (run_ids=[None]) it's equivalent; for future multi-run it diverges from rtl_buddy's "compile-once-pre-once-sim-per-id" guarantee. Also: no "No preproc script provided" info log; spec namespace omits `logger` key in namespace dict (uses `logging.getLogger("preproc")` only). |
| 32 | Early-stop PRE | `RunDepthGate` (`gate_depth=pre`, spec 10) | Full | Generic module + per-instance config. |
| 33 | Filelist write w/ flags | `FilelistGenerate` (spec 11) | Full | Settings preserved (`unroll=True`, `flatten=False`, `strip=False`, `deduplicate=True`). |
| 34 | Filelist `-F` / `-f` / `+libext+` / dir checks | `FilelistGenerate` | Full | Spec 11 lists each behavior to preserve. |
| 35 | Compile command construct | `CompileCommandBuild` (spec 11) | Full | Argv build mirrors rtl_buddy. |
| 36 | Compile subprocess + logging | `CompileExecute` (spec 12) | Partial | Uses async exec (good for harness). But: no transient `\r` duration print; stderr dump is truncated to 500 chars in evidence rather than full error-level dump as rtl_buddy emits. |
| 37 | Compile-fail → one row per run id | `CompileExecute` (spec 12) | **Missing** | Spec 12 emits exactly one failure row per compile, not one per `run_ids`. Plan A `RunFanout` only runs on `success`, so on failure no fan-out occurs. Diverges from `test_runner.py:L99`. Plain `test` unaffected; future randtest reuse breaks. |
| 38 | Early-stop COMP | `RunDepthGate` (`gate_depth=comp`) | Full | Same generic gate. |
| 39 | Multi-run pre/compile-once, sim-per-id | `RunFanout` (spec 13) | Partial | Topologically correct, but spec 13 says `run_ids = [run_plan.key.run_id]` — i.e. fan-out of size 1. Cannot actually emit N sims for one compile until `RunIdPlan` is changed to produce N upstream items; this only happens because preproc is currently post-RunIdPlan. The graph's compile-once semantics for multi-run would need restructuring. |
| 40 | Seed resolve (replay/new/default) | `SeedResolve` (spec 14) | Partial | New (random) and default branches OK. Replay branch reads `<build_dir>/test[_NNNN].randseed`, but rtl_buddy reads `logs/<test_name>[_NNNN].randseed`. Path mismatch breaks replay for any project where seeds were written by rtl_buddy. Also `replay_run_id` can differ from `run_id` (rtl_buddy `vlog_sim.py:L198`); spec 14 derives path only from `run.key.run_id`, ignoring `seed_mode.replay_run_id`. |
| 41 | Replay-failure evidence files | `SeedResolve` | **Missing** | rtl_buddy writes `<log_path>.log` ("FAIL replay seed missing") and `<log_path>.err`, then force-symlinks `test.err`/`test.log` before returning. Spec 14 only emits a `TestResultRow` on `failure`. No compatibility evidence files. |
| 42 | Sim command construct | `SimCommandBuild` (spec 15) | Partial | argv structure matches, but `log_path_prefix` uses `<build_dir>/test[_NNNN]` instead of `logs/<test_name>[_NNNN]`. |
| 43 | Custom-timeout warn | `SimCommandBuild` | Missing | Spec 15 resolves timeout but no warning log. rtl_buddy warns at `vlog_sim.py:L233` when timeout is non-default. |
| 44 | Log path convention `logs/` | none | **Missing** | Plan A doesn't preserve `logs/` output dir; tests would write to `<build_dir>/`. |
| 45 | SIGINT→SIGQUIT graceful Ctrl-C | `SimExecute` (spec 16) | **Missing** | Spec 16 uses `proc.kill()` on timeout. No `os.setpgrp`, no SIGINT handler, no SIGQUIT on timeout. Ctrl-C UX differs. |
| 46 | Randseed file + `hier_inst_seed` append | `SimExecute` (spec 16) | Partial | `.randseed` write covered (step 5). `HierInstanceSeed.txt` append on `hier_inst_seed` substring is omitted. |
| 47 | `force_symlink` to `test.{err,log,randseed}` | `SimArtifactLink` (spec 16) | Partial | Symlinks created in `base_dir` (i.e. `<build_dir>/`), not in cwd. rtl_buddy puts them in cwd. Where downstream tooling expects `./test.log`, this breaks. |
| 48 | Sim timeout → FAIL row; non-zero passes through | `SimExecute` | Full | Spec 16 step 7 + step 8 + closing note. |
| 49 | Early-stop SIM | `RunDepthGate` (`gate_depth=sim`) | Full | Generic gate. |
| 50 | Post parser selection | `PostParserSelect` (spec 17) | Full | Two-line router. |
| 51 | Default log parser (PASS override semantics) | `DefaultLogParser` (spec 17) | Partial | Spec 17 captures override order. But: rtl_buddy concatenates `desc` from FAIL match + ERR/FAT text when both fail-side matches occur (`vlog_post.py:L41`); spec 17 says "desc from matched text" generically. Also missing `^` anchoring nuance: rtl_buddy uses `re.search(r"^PASS\s*(.*)", line)` line-by-line. |
| 52 | UVM parser (regex, thresholds, FATAL=0) | `UvmLogParser` (spec 18) | Partial | Threshold keys: rtl_buddy uses `max_warns`/`max_errors` (`tools/vlog_sim.py:L294`); spec 18 uses `max_warning`/`max_error`. Key-name drift. Pass `desc` text differs (`"UVM: PASS"` vs rtl_buddy's structured `"<n> uvm warnings, <n> uvm errors detected. max_warnings=..."`). |
| 53 | Result default-shape normalisation | `DefaultLogParser`+`UvmLogParser` | Full | §6.27 confirms inline normalisation. |
| 54 | `is_pass()` (PASS+SKIP pass-like) | (encoded in exit-code logic) | Full | Spec 20 documents SKIP must not trigger `log.error`. |
| 55 | Column-formatted summary (`<30`, `<8`, `<30`) | `SummaryRender` (spec 20) | Partial | Spec 20 uses `<40 <6 <desc>`; legacy widths are `<30 <8 <30`. Visible difference. |
| 56 | Exit code accumulation | harness deferred-failure | Full | §6.30 explicit, spec 20 documents `log.error` triggers exit 1. |
| 57 | Transient `\r` blanking | (none) | Missing | Compile/sim timing printouts and the final `print(" "*80, end='\r')` are not reproduced. |
| 58 | Result row shape `{test_name, randmode_i, results}` | `TestResultRow` | Full | `TestInstanceKey` carries `expanded_test_name` + `run_id`; equivalent. |

## Section C — Atomicity assessment

For each Plan A module:

- **`SeedModeSelect`** (spec 02): **Atomic.** Pure CLI-flag-to-enum mapping; no I/O, no scheduling.
- **`RootBootstrap`** (spec 03): **Composite (justified).** Does file discovery, YAML load, platform selection, builder selection, mode defaulting — but rtl_buddy itself binds these together (`RootConfig.__init__`), and splitting would explode into 4–5 trivial modules whose only consumer is each other. Justified single concern: "establish root context."
- **`GitStatusReport`** (spec 22): **Atomic.** Single observability call; the optional-suppression-on-`--list` should be a graph-routing decision (a `ListTestsBranch`-equivalent), not module logic.
- **`SuiteConfigLoad`** (spec 04): **Composite (justified).** Combines suite YAML parse, testbench lookup build, and per-test envelope normalization (plusargs/plusdefines flattening, path resolution). Tight coupling — splitting "parse YAML" from "build envelopes" yields no observable interleaving and forces a redundant intermediate artefact.
- **`ListTestsBranch`** (spec 05): **Atomic.** Pure named-port router on `list_tests` flag.
- **`ListTestsRender`** (spec 05): **Atomic.** One-line string join.
- **`TestSelect`** (spec 05): **Atomic.** Generator that filters by name; one concern.
- **`RegressionLevelSkipFilter`** (spec 06): **Atomic.** Computes `t_lvl`, applies bounds, routes. One concern.
- **`LegacySweepExpand`** (spec 07): **Atomic.** Exec sweep script and yield variants. Single concern: legacy compat hook.
- **`RunIdPlan`** (spec 08): **Atomic.** Generates per-run-id `RunPlan`. Note: the spec drops `cli` input that the master plan and graph YAML still wire — this is a definitional mismatch, not an atomicity issue.
- **`LegacyPreproc`** (spec 09): **Atomic.** Single hook execution.
- **`RunDepthGate`** (spec 10): **Atomic.** Single comparison + branch routing. Reused as three instances — exemplary of "module = computation, contract/graph = scheduling."
- **`FilelistGenerate`** (spec 11): **Composite (justified).** Does extract + process + write. rtl_buddy's `VlogFilelist.write_output` is itself the natural unit; splitting "extract" from "write" creates a `FilelistEntries` artefact with no other consumer. Justified.
- **`CompileCommandBuild`** (spec 11): **Atomic.** Builds argv only; no execution.
- **`CompileExecute`** (spec 12): **Composite (should split)** — minor. Runs the subprocess AND builds the `TestResultRow` on failure. Per §6.27 the rationale for inlining the row was avoiding a fan-in. Acceptable, but the module also encodes failure description ("compile failed") that belongs in a shared compatibility constant. Borderline; **leaving as composite-justified** is defensible.
- **`RunFanout`** (spec 13): **Atomic.** Generator that emits per-run plans.
- **`SeedResolve`** (spec 14): **Composite (should split).** Currently does (a) replay file path computation, (b) replay file I/O + parse, (c) new seed generation, (d) default seed lookup, AND (e) failure-evidence writing (per master plan §6.19, though spec 14 dropped the evidence write — that's a separate gap). The new/default seed paths are trivial; the replay path is the heavy concern. A clean split would be `ReplaySeedRead` (file I/O, fallible) and `SeedSelect` (mode→seed dispatch). Recommended split if replay-evidence compat is restored.
- **`SimCommandBuild`** (spec 15): **Atomic.** argv construction only.
- **`SimExecute`** (spec 16): **Atomic.** Single subprocess + timeout. (Once SIGINT and `hier_inst_seed` features are added they remain part of the single "run sim" concern.)
- **`SimArtifactLink`** (spec 16): **Atomic.** Single concern: symlinking. README acknowledges its small size (justifying co-location in `sim.py`, not co-classing).
- **`PostParserSelect`** (spec 17): **Atomic.** Two-line router.
- **`DefaultLogParser`** (spec 17): **Atomic.** Single parse pass.
- **`UvmLogParser`** (spec 18): **Atomic.** Single parse pass.
- **`SuiteResultAccumulate`** (spec 19): **Atomic.** Append-on-run + sort-on-finalise. Behaves as a sink. Uses `FanInContract` (in `contracts/`), correctly leaving scheduling out of the module.
- **`SummaryRender`** (spec 20): **Atomic.** Pure formatter.

**No module owns scheduling logic.** All scheduling lives in graph edges + the `latest` / `zip` / `default` / `fan_in` contracts and the new `FanInContract`. The harness/contract split is respected throughout.

## Section D — Gap list (prioritised; functional → atomicity → minor)

### Functional gaps (affect behaviour relative to rtl_buddy)

1. **Root config YAML schema mismatch** — Spec 03 step 2 assumes top-level keys `platform`/`builder`; rtl_buddy's serde schema uses `cfg-platforms`, `cfg-rtl-builder`, `cfg-rtl-reg`, `rtl-buddy-filetype` (`config/root.py:L42-L48`). `RootBootstrap` cannot load any real rtl_buddy `root_config.yaml` without fixing this. **Highest severity** — graph won't bootstrap.
2. **Suite config YAML schema mismatch** — Spec 04 step 2 assumes `testbenches` (dict). rtl_buddy uses `testbenches: list[TestbenchConfig]` with explicit `rtl-buddy-filetype: test_config` discriminator (`config/suite.py:L11-L15`). Same severity — graph cannot load real `tests.yaml`.
3. **Replay seed path divergence** — Spec 14 reads `<build_dir>/test[_NNNN].randseed`; rtl_buddy writes to `logs/<test_name>[_NNNN].randseed` (`tools/vlog_sim.py:L82-L86,L263`). Replay flow will never find existing seeds.
4. **`logs/` output-dir convention not preserved** — Spec 11/15 anchor all paths under `<build_dir>/`; rtl_buddy uses a flat `logs/` directory (`tools/vlog_sim.py:L55-L58`). Affects spec 14, 15, 16; downstream tooling that greps `logs/` for results breaks.
5. **Compile-fail row cardinality** — Spec 12 emits one `failure` row per compile; rtl_buddy emits one per `run_id` (`runner/test_runner.py:L99`). Plain `test` is unaffected (`run_ids=[None]`); regression/randtest reuse will silently lose rows.
6. **Skip row cardinality** — Spec 06 emits one `skip` row per filtered test; rtl_buddy emits one per `run_id` (`rtl_buddy.py:L259-L262`). Master plan §6.9 listed `run_ids` as input but spec 06 dropped it. Same severity profile as #5.
7. **`RunFanout` does not actually fan out** — Spec 13 derives `run_ids` from `compile_result.command.run_plan.key.run_id` (a single value), so the fan-out is degenerate. Together with #5/#6, this means Plan A is currently `test`-only and cannot be reused for `randtest`/`regression` despite the master plan claiming it preserves that pathway.
8. **Replay-failure evidence files missing** — Spec 14 omits the `<log_path>.log`/`.err`/`test.{log,err}` symlinks that rtl_buddy writes on replay-seed failure (`tools/vlog_sim.py:L204-L211`). Compatibility regression for tools that scrape these files.
9. **SIGINT/SIGQUIT signal handling not preserved** — Spec 16 uses `proc.kill()`; rtl_buddy installs SIGINT→SIGQUIT, uses `os.setpgrp`, and on timeout sends SIGQUIT (`tools/vlog_sim.py:L243-L262`). Ctrl-C and timeout-cleanup behaviour differs.
10. **`hier_inst_seed` augmentation missing** — Spec 16 step 5/6 omits the `HierInstanceSeed.txt` append branch (`tools/vlog_sim.py:L265-L269`).
11. **`SimArtifactLink` writes symlinks in `base_dir`** — Spec 16 puts `test.log` etc. in the sim's directory; rtl_buddy puts them in cwd (`tools/vlog_sim.py:L271-L273`). Convention break.
12. **Sweep `TestConfig` namespace binding** — Spec 07 binds `TestConfig` to `TestConfigEnvelope`; legacy sweep scripts written for rtl_buddy's `TestConfig` (`config/test.py:L43-L80` — positional `name, desc, model, _reglvl, …`) will not survive. Sweep scripts are a compatibility-sensitive API per `AGENTS.md`.
13. **`reglvl` malformed-config handling differs** — Spec 06 silently returns `t_lvl=0` on missing builder key; rtl_buddy calls `logger.critical` if neither builder-key nor `default` is present (`config/test.py:L290-L297`).
14. **UVM threshold key name mismatch** — Spec 18 reads `max_warning`/`max_error`; rtl_buddy reads `max_warns`/`max_errors` (`tools/vlog_sim.py:L294`). User UVM configs will appear to silently use the default `0`.
15. **UVM pass-row `desc` shape differs** — Spec 18 uses `"UVM: PASS"`; rtl_buddy emits the structured `"<n> uvm warnings, <n> uvm errors detected. max_warnings=<x>, max_err=<y>"` (`tools/vlog_post.py:L74-L77`). Visible diff in summary.
16. **Default parser `desc` composition** — Spec 17 step 4 generic; rtl_buddy concatenates the FAIL match group with the ERR/FAT match group (`tools/vlog_post.py:L41`). Likely descriptive-text regressions.
17. **`builder_override` callback validation absent** — Spec 03 doesn't pre-validate against discovered builder names (`rtl_buddy.py:L70-L81`); fatal moves from "bad parameter" to "configuration error during bootstrap." UX regression.
18. **Platform-uname comparison differs** — Spec 03 lower-cases `platform.uname().system`; rtl_buddy compares exact uname stdout to `cfg-platforms[i].unames` list (`config/root.py:L107-L114`).
19. **Custom-timeout warning lost** — Spec 15 resolves the timeout but never logs `"Using custom sim_timeout of N seconds"` (`tools/vlog_sim.py:L233-L234`).
20. **PATH `.` prepend missing** — `rtl_buddy.py:L101-L102` is required so locally-built simv executables can be invoked. Spec 03 (the only candidate for early-startup work) omits this.
21. **Plan A's `LegacyPreproc` is downstream of `RunIdPlan`** — for plain `test` this is equivalent (only one run id), but rtl_buddy guarantees `pre()` runs **once per expanded test** before any sim (`runner/test_runner.py:L92-L99`). For future `randtest`/`regression` reuse this breaks the contract. The fix is structural (move `LegacyPreproc` above `RunIdPlan` and `RunFanout`).
22. **Summary column widths differ** — Spec 20 uses `<40 <6`; rtl_buddy uses `<30 <8 <30` (`rtl_buddy.py:L205`).
23. **`RESULT` log channel missing** — rtl_buddy uses level 25 to render the final summary line via `logger.result(...)`. Spec 20 returns a `RenderedOutput` but does not register the level. If the harness logger ignores anything below WARNING in console mode, the summary becomes invisible.
24. **Spec drift: `git-status` in spec 22 still expects `TestCliArgs`** — Spec 21 removed `CliArgsMerge`; spec 22 must be updated to take CLI edges directly.
25. **Spec drift: `RunIdPlan` `cli` input** — Master plan §6.11 and graph YAML edges (master plan L1802) still wire `cli` to `run-id-plan`, but spec 08 only declares `expanded_test` and `seed_mode`. Module will fail validation on the third input or silently ignore it.

### Atomicity / structural issues

26. **`SeedResolve` should be split** — separate `ReplaySeedRead` (fallible I/O) from `SeedSelect` (mode→seed dispatch). The replay path also needs to write evidence files (gap #8), which is itself a separable concern (`ReplayFailureRecord`).
27. **`RunDepthGate` reuse is exemplary** — call this out as the model for any future early-stop or routing modules.

### Minor / cosmetic

28. **No `\r`-blanking and no compile/sim transient duration printout** — the print at `rtl_buddy.py:L368` and the two `print("test %s vlog … time %d secs\r")` calls in vlog_sim are absent.
29. **No version banner / no ANSI colouriser** — `--color` CLI flag passes through but nothing consumes it.
30. **`evidence` shape is undefined** — `TestResultRow.evidence: dict[str, str]` varies across producers (compile uses `returncode`/`stderr`, sim uses `timeout_seconds`, parsers use `log`). Worth standardising before downstream renderers/CI integrations read it.

## Section E — Summary

Plan A's structural decomposition is solid: 24 modules across 7 files, each cleanly mapped to one rtl_buddy concern, with scheduling pushed into the new `FanInContract` plus reuse of the existing `latest`/`zip`/`default` contracts. The harness/contract/module split is respected throughout — no module owns scheduling, and `RunDepthGate`'s single-class/three-instance pattern is an exemplary atomic-module reuse story. Of the 24 modules, 22 are atomic or composite-justified by rtl_buddy's own bundling; only `SeedResolve` clearly warrants a further split, and even that becomes critical only once the replay-evidence and replay-path bugs are fixed.

Coverage of the rtl_buddy `test` flow is broadly present (rated Full for ~25 of the 58 concerns, Partial for ~22, Missing for ~8), but the partials hide load-bearing breakages: the two YAML schema mismatches (#1, #2) mean the graph will not bootstrap against any real rtl_buddy project, and the path-convention drift away from `logs/` (#3, #4, #11) silently breaks replay, downstream tooling, and the `test.*` symlink contract. The biggest weakness is therefore **fidelity to rtl_buddy's filesystem and YAML surface**, not the graph decomposition: a user running `rtl-comrade test` in an existing rtl_buddy project would hit a bootstrap error before any module logic mattered. Secondary weakness is **multi-run cardinality** (skip rows, compile-fail rows, preproc-per-expansion, RunFanout degeneracy): Plan A is a correct port of *plain* `test` but cannot be reused for `randtest`/`regression` without the four structural fixes called out in gaps #5–#7 and #21.
