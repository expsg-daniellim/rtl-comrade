# To Do

## Docs

- **Authoritative example graph** — author a dedicated graph YAML that covers all config features and can serve as the canonical reference. Currently `graphs/graph2.yaml` is used as a stand-in. (`docs/harness_configs/graph.md`)

- **Concrete first-run example in `running.md`** — once the end-to-end flow is complete, add a worked example showing a real command and its output. (`docs/running.md`)

## Harness

- **Normalise config paths** — graph paths in `rtl_comrade_config.yaml` are resolved relative to the runner's working directory, not relative to the config file's location. (`src/rtl_comrade/app.py:70`)

- **Debug logging in `__main__.py`** — noted as a TODO with no further detail. (`src/rtl_comrade/__main__.py:5`)
