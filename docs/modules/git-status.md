# `git-status`

**Class:** `GitStatusMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Logs the current git branch, SHA, and dirty flag for run provenance. Emits a token but performs no gating; it is a best-effort side effect.

## Inputs

None — source node.

## Outputs

`default` — `True`.

## Failure routing

`log.warning` (`git_state_unavailable`) if git is missing or the commands fail — a non-git tree is not an error.

## Graph node

`git-status`, contract `default`.
