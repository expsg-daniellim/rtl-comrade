# Creating Documentation

See also:

- [CLAUDE.md](/Users/daniellim/Documents/random/rtl-comrade/CLAUDE.md) — the routing table this doc describes
- [docs/contributing.md](/Users/daniellim/Documents/random/rtl-comrade/docs/contributing.md) — contribution process and seam discipline

## Guiding principle: atomicity

Each doc should cover exactly one concern. An agent reading a doc to complete a task should not have to load unrelated content to get to what it needs. If a file covers two concerns that are never needed together, it should be two files.

The test: if you would only ever read section A when doing task X and only ever read section B when doing task Y, and X and Y are distinct, those sections belong in separate files.

## What belongs in `CLAUDE.md`

`CLAUDE.md` is loaded on every interaction. Keep it short. It should contain only:

- A brief architecture overview (what the project is and its major layers)
- Standing instructions that apply to every task (e.g. "always follow code-style.md")
- A routing table mapping task types to the docs that must be read first
- A fallback command for tasks not covered by the table
- Pointers to running and testing docs

Everything else belongs in `docs/`. Do not put authoring rules, config details, invariants, or process guidance in `CLAUDE.md` — those have their own files and are loaded only when relevant.

## Directory structure

```
docs/
  harness/          one file per harness source module
  modules/          implementation.md + testing.md
  contracts/        implementation.md + testing.md + index.md + one file per contract
  harness_configs/  index.md + one file per config file format
```

Top-level files in `docs/` are project-wide concerns that don't belong to a specific layer: `running.md`, `testing.md`, `code-style.md`, `contributing.md`, `invariants.md`, `creating-documentation.md`.

## When to split a file

Split when:

- A section is only needed for a specific task and the rest of the file is not
- A section is long enough to dominate the file and obscures the rest
- Two sections serve different audiences (e.g. implementation guidance vs. testing guidance)

Do not split when:

- The sections are always read together
- The split would produce files too small to be worth navigating to separately
- The content is already at the right granularity (a short harness module doc does not need further splitting)

## Directory indexes

Any directory containing multiple related files of the same kind should have an `index.md` that lists and briefly describes each file. This makes the directory navigable without requiring a `find` command. The contracts and harness_configs directories follow this pattern.

## Routing table entries

When adding a new doc, consider whether it warrants a row in `CLAUDE.md`'s routing table. Add a row only if the doc is a prerequisite for a specific class of task. Docs that are reached naturally by following links from existing table entries do not need their own row.

## Cross-references

Link to related docs at the top of a file, not inline in the body. A reader deciding whether to read the file should see its dependencies upfront. Use absolute file paths for links (the existing harness docs follow this convention).

When a doc mentions a concern covered elsewhere, add a pointer rather than duplicating the content. Duplication drifts.

## Moving or deleting docs

Before moving or deleting a file:

1. Read the file to confirm its full contents — do not rely on memory of what it contains.
2. Check for references with `grep -r "<filename>" docs/ CLAUDE.md`.
3. If moving: create the new file first, then replace the old file with a one-line redirect stub pointing to the new location.
4. Update any references found in step 2.
5. Once all references are updated and you have confirmed the redirect stub is the only content remaining, delete the stub.

Deletions are irreversible. Read before acting.

## After writing a doc

Re-read the finished file and apply the atomicity test to every section: would this section ever be needed without the others? If any section fails the test, split it out before considering the task done. This applies to the file you just wrote, not only to files you are reviewing.

