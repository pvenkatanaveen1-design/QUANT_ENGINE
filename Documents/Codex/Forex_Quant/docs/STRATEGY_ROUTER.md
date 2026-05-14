# Strategy Router

The router is the bridge from detected regime to strategy candidates. It prevents the platform from evaluating every idea at once.

Rules:

- The registry has 52 regimes x 4 slots = 208 names.
- Slots are `primary`, `secondary`, `confirmation`, and `fallback`.
- Research mode shows all four candidates for inspection.
- Paper mode returns only enabled strategies with `paper_approved` or `live_approved` status.
- Live mode returns only enabled, `live_approved`, `live_allowed` strategies.
- All current entries are disabled and `not_tested`, so live trading cannot use them.

Status lifecycle:

```text
name_only -> logic_added -> backtested -> walk_forward_passed -> monte_carlo_passed -> paper_approved -> live_approved -> retired
```

