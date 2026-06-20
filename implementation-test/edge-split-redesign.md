# Edge-split redesign — authoritative design

**Status:** ACTIVE. The blocker is resolved — commit `3068cda` (`feat: persistent port support for keyed_join`) lets a `keyed_join` node declare `persistent_inputs`, so the full bag-split is buildable. This doc is the source of truth; the per-ticket edits below apply it.

## Goal

Replace the two accreted context-bags — `ctx` (`{key, test, run_id, simv, seed}`) and `test_run` (`{key, test, run_id, rc, timed_out, log, err, randseed_path}`) — with explicit per-field keyed edges. Bags that are produced as a unit by one node stay whole (`proc`, `command`, `filelist`, `randseed`, `seed`); bags assembled across the graph are split.

## Conventions (apply uniformly)

- **C1 — edge payload shape.** A *single-value* split edge carries `{key, value}` — the port/edge name already says what it is, so the field is the generic `value`: `test{key,value}`, `simv{key,value}`, `run_id{key,value}`, `seed{key,value}`, `timeout{key,value}`, `filelist{key,value}`. Inside a node, read `test["value"]`, `simv["value"]`; the key is `<any-port>["key"]` (all joined ports share it). *Multi-field cohesive messages are not wrapped* — they keep named fields: `proc{key,rc,timed_out,stdout_path,stderr_path}`, `command{key,argv,stdout_path,stderr_path}`, `randseed{key,seed,randseed_path,argv}` (read `proc["rc"]`, `command["argv"]`, `randseed["randseed_path"]`). The unwired **result diversion edges** (`skip`/`fail`/`timeout` ports → a `TestResults`) keep `{key, result}`: their port already names the *route* not the payload, they are terminal (no node consumes them), so `value` would lose the only descriptor they have.
- **C2 — one output port per forwarded edge.** A router emits each co-gated edge on its own named port; success-vs-fail is expressed by *which* ports fire (e.g. `interpret-compile` fires `test`+`simv` on success, `fail` on failure — there is no single "ok" port carrying a bundle).
- **C3 — contract rule.** One keyed stream + singletons → stays `default` with `persistent_inputs`. Two-or-more keyed streams → `keyed_join` with `persistent_inputs` for the singletons. (This is the capability commit `3068cda` unlocked.)
- **C4 — `timeout` is a separate edge `{key, value}`, NOT folded into `command`.** `command` must stay a uniform `{key, argv, stdout_path, stderr_path}` message, and it legitimately exists *without* `timeout` on the compile leg — folding would make `command` polymorphic (the bag anti-pattern). So the sim `run-process` instance becomes `keyed_join(command, timeout)` + `persistent_inputs:[env_ready]`; the compile instance stays `default(command)` + `persistent_inputs:[env_ready]` (timeout unwired → module default `None`). Contract differs **per node instance**; the shared `run-process` module signature is unchanged (`command`, `timeout=None`, `env_ready`). Touches spec 03 only in that its sim wiring is now a keyed_join (no code change).
- **C5 — `test_run` is dissolved.** No assembly node. `write-randseed` becomes a side-effect leaf. Post-sim is two parallel branches off `proc`.

## Bag lifetimes (what the split exposes)

- `test` — `select-tests` → `parse-*` (long-lived; the only edge threading the whole pipeline).
- `simv` — born `build-compile-cmd`, dies `build-sim-cmd`. Re-keyed across the fan-out by `expand-runs`.
- `run_id` — born `expand-runs`, dies `build-sim-cmd` (only lives in the key suffix and the already-composed paths thereafter). **Not** present pre-`expand-runs` (no more `run_id:None` placeholder) and **not** present post-`build-sim-cmd`.
- `seed` — born `resolve-seed`, dies `build-sim-cmd` (consumed into `randseed` + the sim argv).

## Node / contract / edge table

`key` rides every edge. Singletons (`builder_cfg`, `builder_mode`, `logs_dir`, `work_dir`, `seed_mode`, `root_cfg`, `run_ids`) are `persistent_inputs` on whatever contract the node uses.

| node | contract | keyed streams in | persistent in | emits |
|---|---|---|---|---|
| select-tests | default | suite_cfg | — | `test{key,test}` |
| filter-reglvl | default | test | builder_cfg, reg_level, start_level | `test` / skip:result |
| load-model | default | test | — | `test`(+model) / fail:result |
| expand-sweep | default·gen | test | root_cfg | `test` ×N (key#i) / fail:result |
| run-preproc | default | test | root_cfg | `test` / fail:result |
| write-filelist | default | test | work_dir | `test` + `filelist{key,filelist}` / fail:result |
| build-compile-cmd | **keyed_join** | test, filelist | builder_cfg, builder_mode, logs_dir, work_dir | `test` + `simv{key,simv}` + `command` |
| run-process #1 (cc) | default | command | env_ready | `proc{key,rc,timed_out,stdout_path,stderr_path}` |
| interpret-compile | keyed_join | test, simv, proc | — | (`test`+`simv`) / fail:result |
| expand-runs | **keyed_join**·gen | test, simv | run_ids | (`test`+`run_id`+`simv`) ×N (key#r) |
| resolve-seed | **keyed_join** | test, run_id, simv | seed_mode, builder_cfg, logs_dir | (`test`+`run_id`+`simv`+`seed`) / fail:result |
| build-sim-cmd | **keyed_join** | test, run_id, simv, seed | builder_cfg, builder_mode, logs_dir | `command` + `timeout{key,value}` + `randseed{key,seed,randseed_path,argv}` + `test` |
| run-process #2 (sim) | **keyed_join** | command, timeout | env_ready | `proc` |
| **— bag boundary —** | | | | |
| write-randseed | keyed_join | randseed, proc(gate) | — | `randseed_done{key}` |
| link-latest | keyed_join | randseed, proc, randseed_done | — | — (terminal side-effect) |
| interpret-sim | keyed_join | test, proc | — | (`test`+`proc`) / timeout:result |
| route-post | keyed_join | test, proc | — | uvm:(`test`+`proc`) / plain:(`test`+`proc`) |
| parse-log / parse-uvm-log | keyed_join | test, proc | — | result |

`proc` echoes `stdout_path`/`stderr_path` (= log/err), so post-sim reads those paths from `proc` — no separate log/err edges, and `sim_cmd` disappears entirely (its parts become `command` + `randseed`).

## The two careful nodes

**`expand-runs` (per-test → per-run fan-out + re-key).** `keyed_join(test, simv)` at the test-level key, `persistent_inputs: [run_ids]`, generator output. For each `run_id`:
```
nk = key if run_id is None else f"{key}#{run_id}"
yield ("test",   {"key": nk, "test": test["test"]})
yield ("run_id", {"key": nk, "run_id": run_id})
yield ("simv",   {"key": nk, "simv": simv["simv"]})
```
It rebroadcasts `test`+`simv` (consumed at the test key) plus the new `run_id`, all at each run key.

**`write-randseed` (side-effect leaf, no assembly).** `keyed_join(randseed, proc)`. `proc` is only a completion gate (ignores `rc`/`timed_out`). Writes `randseed["randseed_path"]` from `randseed["seed"]`, appends `HierInstanceSeed.txt` iff `"hier_inst_seed" in randseed["argv"]`, then `yield ("randseed_done", {"key": randseed["key"]})`. It does **not** read `test` or `run_id`.

## Co-gating rule

Every failure-routing node (`filter-reglvl`, `load-model`, `run-preproc`, `write-filelist`, `interpret-compile`, `resolve-seed`, `interpret-sim`) must **forward every edge a downstream join needs on its success branch**. A field that bypasses a router dangles the downstream `keyed_join` on the router's fail branch (its key never completes — verify whether the harness hangs or just leaks; either way co-gate). In the table above each router's success row lists exactly the edges it forwards.

## Per-ticket change checklist

- **[DONE] Stage 1 — default pre-sim nodes:** [x] 05c select-tests, [x] 05d filter-reglvl, [x] 05e load-model, [x] 05f expand-sweep, [x] 06a run-preproc, [x] 06b write-filelist.
- **[DONE] Stage 2 — keyed_join flips (compile cycle):** [x] 07a build-compile-cmd (`keyed_join(test,filelist)`+persist; emits `test`+`simv`+`command`), [x] 07b interpret-compile (`keyed_join(test,simv,proc)`; co-gates `test`+`simv` / fail), [x] 03 run-process (sim instance `keyed_join(command,timeout)`; reads `timeout["value"]`; tests wrap timeout — decision **A**).
- **[DONE] Stage 3 — keyed_join flips (sim cycle):** [x] 08a expand-runs (`keyed_join(test,simv)`+persist[run_ids], re-keys `test`/`run_id`/`simv` per run; `run_suffix(run_id)` helper updated), [x] 08b resolve-seed (`keyed_join(test,run_id,simv)`+persist; forwards all + `seed`, co-gated), [x] 08c build-sim-cmd (`keyed_join(test,run_id,simv,seed)`+persist; emits `command`+separate `timeout{key,value}`+`randseed`+`test`; `sim_cmd` removed; `simv`/`run_id`/`seed` die here).
- **[DONE] Stage 4 — post-sim dissolve:** [x] 08d write-randseed (side-effect leaf `keyed_join(randseed,proc-gate)`, emits `randseed_done`, no `test_run`), [x] 08e link-latest (`keyed_join(randseed,proc,randseed_done)`, terminal), [x] 08f interpret-sim (`keyed_join(test,proc)`, forwards both on clean run), [x] 09a route-post (`keyed_join(test,proc)`, co-routes both — 4 ports, documented exception), [x] 09b parse-log, [x] 09c parse-uvm-log (`keyed_join(test,proc)`; log = `proc["stdout_path"]`). `test_run` fully dissolved; post-sim is two parallel branches off `proc`.
- **Stage 5 — assembly (in progress):** [x] 10a early-stop-gate (`**kwargs` co-gating; gate-pre/comp wired `{test}`, gate-sim `{test, proc}`; uniform module), [x] 11 graph-and-manifests (wiring references redirected to this doc; manifest unchanged). [ ] explicit edge-wiring list (now unblocked), [ ] parent `02-payload-conventions.md` (Shapes 1/`ctx` and 1b/`test_run` need a full rewrite to the split-edge model — substantial).

## Early-stop gates — co-gate via `**kwargs` (RESOLVED)

The three early-stop gates use **one** module with a `**edges` signature: the harness populates each instance's keyed input ports from the graph edges wired to it (the non-definite-inputs support, `graph.py:95-97`; settled 19/21/22). So:

- `gate-pre` / `gate-comp` are wired `{test}` — contract `default`.
- `gate-sim` is wired `{test, proc}` — contract `keyed_join`.

On **"go"** the gate forwards *every* input edge on its same-named output port (co-gating all of them); on **"stop"** it drops them and emits a `{key, result}`. Identity always comes from `edges["test"]`. This keeps the gate uniform across instances and co-gates whatever flows past each one — `gate-sim` drops `test`+`proc` together on a stop, so `route-post`'s join can't dangle. No specialized module, no folding into `interpret-sim`. See spec 10a.

## Edge-wiring list (the graph)

Producer `node.port` → consumer `node.port`. Singletons fan out as `persistent_inputs` (one source → many consumers is fan-out, allowed; only *inputs* must be single-source). `cc-run`/`sim-run` are the two `run-process` instances.

**Setup → persistent fan-out:**
- discover-config-file.default → parse-root-config.path
- parse-root-config.default → {select-platform.root_cfg, resolve-builder.root_cfg, expand-sweep.root_cfg(persist), run-preproc.root_cfg(persist)}
- select-platform.default → resolve-builder.platform_cfg
- resolve-builder.default → {filter-reglvl, build-compile-cmd, resolve-seed, build-sim-cmd}.builder_cfg (persist)
- check-suite-cwd.default → parse-suite-config.test_config_path ; check-suite-cwd.work_dir → {ensure-logs-dir, write-filelist, build-compile-cmd}.work_dir (persist)
- ensure-logs-dir.logs_dir → {build-compile-cmd, resolve-seed, build-sim-cmd}.logs_dir (persist)
- parse-suite-config.default → route-list-mode.suite_cfg
- derive-seed-mode.default → resolve-seed.seed_mode (persist)
- prepend-cwd-path.default → {cc-run, sim-run}.env_ready (persist)
- git-status.default → (unwired)
- CLI persistents: builder→resolve-builder; reg_level/start_level→filter-reglvl; builder_mode→{build-compile-cmd, build-sim-cmd}; run_ids→expand-runs; early_stop→{gate-pre, gate-comp, gate-sim}; rnd_new/rnd_last→derive-seed-mode; test_config→check-suite-cwd; logs_dir(str)→ensure-logs-dir; list→route-list-mode; test_name→select-tests

**List-mode:** route-list-mode.list → list-test-names.suite_cfg ; route-list-mode.run → select-tests.suite_cfg

**Per-test chain:**
- select-tests.test → filter-reglvl.test
- filter-reglvl.test → load-model.test ; *.skip → ∅
- load-model.test → expand-sweep.test ; *.fail → ∅
- expand-sweep.test → run-preproc.test ; *.fail → ∅
- run-preproc.test → gate-pre.test ; *.fail → ∅
- gate-pre.test → write-filelist.test ; *.stop → ∅
- write-filelist.test → build-compile-cmd.test ; write-filelist.filelist → build-compile-cmd.filelist ; *.fail → ∅
- build-compile-cmd.command → cc-run.command ; build-compile-cmd.test → interpret-compile.test ; build-compile-cmd.simv → interpret-compile.simv
- cc-run.default(proc) → interpret-compile.proc
- interpret-compile.test → gate-comp.test ; interpret-compile.simv → gate-comp.simv ; *.fail → ∅
- gate-comp.test → expand-runs.test ; gate-comp.simv → expand-runs.simv ; *.stop → ∅
- expand-runs.{test,run_id,simv} → resolve-seed.{test,run_id,simv}
- resolve-seed.{test,run_id,simv} → build-sim-cmd.{test,run_id,simv} ; resolve-seed.seed → build-sim-cmd.seed ; *.fail → ∅
- build-sim-cmd.command → sim-run.command ; build-sim-cmd.timeout → sim-run.timeout ; build-sim-cmd.randseed → {write-randseed.randseed, link-latest.randseed} ; build-sim-cmd.test → interpret-sim.test
- sim-run.default(proc) → {write-randseed.proc, link-latest.proc, interpret-sim.proc}

**Post-sim — side-effect branch:** write-randseed.randseed_done → link-latest.randseed_done ; link-latest = terminal (no output)

**Post-sim — classification branch:**
- interpret-sim.test → gate-sim.test ; interpret-sim.proc → gate-sim.proc ; *.timeout → ∅
- gate-sim.test → route-post.test ; gate-sim.proc → route-post.proc ; *.stop → ∅
- route-post.{uvm_test,uvm_proc} → parse-uvm-log.{test,proc} ; route-post.{plain_test,plain_proc} → parse-log.{test,proc}
- parse-log.default → ∅ ; parse-uvm-log.default → ∅

**The 13 unwired terminal (∅) ports:** filter-reglvl.skip; {load-model, expand-sweep, run-preproc, write-filelist, interpret-compile, resolve-seed}.fail; interpret-sim.timeout; {parse-log, parse-uvm-log}.default; {gate-pre, gate-comp, gate-sim}.stop. (Count unchanged from the bag design — the split renamed the carried payloads, not the result-diversion set.)

## Open items to verify against the harness

- Does a `keyed_join` **hang** on a key whose ports never all complete, or just leak a pending entry? Determines how hard co-gating must be enforced.
- Is `run_ids` static-at-launch (could be module `Config` on `expand-runs`, dropping a persistent) or runtime? Table assumes runtime → persistent.
