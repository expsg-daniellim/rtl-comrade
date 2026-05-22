# Contribution Rules

## Seam discipline

Changes stay local to the seam being edited. The harness, contracts, and modules are distinct layers — do not let concerns bleed across them.

## Feature workflow

1. Implement the feature.
2. Write tests and reach the coverage targets in `docs/testing.md`.
3. Update documentation — see below for what to update.

Do not skip step 3. Tests confirm the code works; docs ensure the next agent or developer understands it.

## Docs updates

After tests pass, update docs for everything that changed:

- New harness module → add a file to `docs/harness/` following the structure in `docs/harness/doc-structure.md`, and add it to the file map in `docs/harness/README.md`.
- Harness behaviour change affecting plugin authoring → update the relevant file in `docs/harness/`.
- New contract → add a file to `docs/contracts/` following `docs/contracts/doc-structure.md`, and add it to `docs/contracts/index.md`.
- New module → update `docs/modules/implementation.md` if authoring rules changed.
- Config shape, port semantics, or plugin loading change → update `docs/harness_configs/` and the sample graph and manifests in the same commit.
- New invariant → add it to `docs/invariants.md`.
- Known gap resolved → remove it from `docs/todo.md`.

## Examples

Prefer executable examples when introducing runtime behaviour. New runtime features should be demonstrable via a graph + module + contract triple that can actually run.

## Authoritative documents

- Do not treat `README.md` as the authoritative architecture document.

## Tests

See `docs/testing.md` for the full two-stage procedure. Every new harness module, contract, and module file needs a corresponding test file reaching 100% coverage before merging.
