# Build Prompts

This repo keeps the original prompt pack in `docs/BUILD_PROMPTS_SOURCE.md`. The working build order is:

1. Data setup and project foundation.
2. Regime detection engine.
3. Strategy registry and regime router.
4. Strategy template logic.
5. Risk analysis and funded-account protection.
6. Backtest and historical trust.
7. Decision orchestrator.
8. UI control center.
9. Paper execution.
10. MT5 safe integration.

Current implementation covers a fast first pass through phases 1, 2, 3, 5, 7, and 8, with phases 4, 6, 9, and 10 intentionally staged behind safety gates.

Next prompt to run:

```text
Build Phase 4: implement the first 8 reusable strategy templates. Keep the 208 registry entries disabled. Strategy templates may emit paper-only signals, but they must not size positions or place orders.
```

