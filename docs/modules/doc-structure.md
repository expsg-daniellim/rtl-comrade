# Module Doc Structure

[Back to index](index.md)

Each module in `modules/rtl_buddy/` gets its own file, named after its plugin name (e.g. [`parse-log.md`](parse-log.md)). One file per module keeps each page atomic: an agent reading up on one module never has to load another's detail. This follows the [atomic-docs principle](../creating-documentation.md#guiding-principle-atomicity) and mirrors the one-file-per-contract layout in [docs/contracts/](../contracts/).

Each file covers:

- **Heading + class** — `` # `plugin-name` `` and `**Class:** \`ClassName\` (source file)`, then `[Back to index](index.md)`
- **Purpose** — one paragraph on what the module does
- **Inputs** — a table of each `run(...)` parameter: port, type, default (if any), and what it carries; note which arrive as persistent config vs. per-test/per-run edges. Source nodes state "None — source node."
- **Config** — the nested `Config` schema with a YAML example, if the module has one
- **Outputs** — each emitted port and when it fires
- **Failure routing** — how caught exceptions map to `log.fatal` (abort), `log.error` (deferred non-zero exit), or a `fail`/`skip` result port (omit if the module has none)
- **Graph node** — the `id` the `test` graph gives this module and the contract it is paired with

Keep pages focused on *using and understanding the one module*. Link to a sibling module rather than restating it (e.g. the compile pages link to [run-process](run-process.md)). Contract/scheduling semantics belong in [docs/contracts/](../contracts/); the `run(...)`→ports mechanics belong in [docs/module-implementation/implementation.md](../module-implementation/implementation.md).
