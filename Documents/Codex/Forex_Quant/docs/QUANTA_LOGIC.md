# Quanta Forex Logic

The canonical logic document is `docs/QUANTA_LOGIC_BLUEPRINT.md`.

Implementation decisions made in this repo:

- Use a dependency-light core first: CSV, YAML, dataclasses, FastAPI, Jinja, HTMX.
- Keep pandas, DuckDB, Plotly, and MetaTrader5 out of the first install unless the next phase needs them.
- Store the full 208-name registry in `config/strategy_registry.yaml`.
- Treat every strategy as `not_tested`, `enabled=false`, and `live_allowed=false`.
- Classify regimes before selecting strategies.
- Block live trading by architecture, not just by UI text.
- Treat MT5 demo integration as a later safe-mode phase.

