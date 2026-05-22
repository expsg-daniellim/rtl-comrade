# Contribution Rules

## Seam discipline

Changes stay local to the seam being edited. The harness, contracts, and modules are distinct layers — do not let concerns bleed across them.

## Docs updates

- If harness behaviour affecting plugin authoring changes → update `docs/harness/`.
- If config shape, port semantics, or plugin loading changes → update the sample graph and manifests in the same commit.

## Examples

Prefer executable examples when introducing runtime behaviour. New runtime features should be demonstrable via a graph + module + contract triple that can actually run.

## Authoritative documents

- Do not treat `README.md` as the authoritative architecture document.

## Tests

See `docs/testing.md` for the full two-stage procedure. Every new harness module, contract, and module file needs a corresponding test file reaching 100% coverage before merging.
