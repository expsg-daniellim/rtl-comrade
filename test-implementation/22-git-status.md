# Spec 22: GitStatusReport (Optional)

## What this covers

Implement `GitStatusReport` in `modules/rtl_buddy_compat/git_status.py`. This is purely observability — it does not affect graph results, exit code, or any downstream computation. Implement it last or skip it entirely if not needed.

## Prerequisites

Spec 00 (artefacts) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L117-L120` — when git status is shown
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L421-L449` — `_print_git_status()` implementation

## File: `modules/rtl_buddy_compat/git_status.py`

### `GitStatusReport`

```
contract: zip
inputs:  cli: TestCliArgs, root: RootContext
outputs: default → GitStatusArtefact
```

Implementation steps:
1. Run `git -C <root.project_root> status -sb` via `subprocess.run()`.
2. Run `git -C <root.project_root> log -1 --pretty=%h`.
3. Parse branch name from the `## ` prefix line of `status -sb`.
4. Format a summary string matching `rtl_buddy.py:L421-L449`.
5. Emit `GitStatusArtefact(branch=branch, commit=commit_hash, text=formatted_text)`.

May use `subprocess.run()` — git is fast enough that blocking is acceptable.

Compatibility: `rtl_buddy.py:L421-L449`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Append to `files`:

```yaml
- file: git_status.py
  plugins:
  - name: git_status_report
    class_name: GitStatusReport
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_git_status.py`.

- In a temp directory with an initialized git repo: verify `GitStatusArtefact` contains branch and commit info.
- In a non-git directory: module should not crash; emit a `GitStatusArtefact` with placeholder values.

## Note on graph wiring

`GitStatusReport`'s output is not connected to `SuiteResultAccumulate`. It is a terminal observability node. If building the graph YAML before this spec is done, wire `cli-args` and `root-bootstrap` to `git-status` and leave its output unconnected or routed to a `StdoutMod`.

## Constraints

- Must not affect result rows, exit code, or any other node's scheduling.
