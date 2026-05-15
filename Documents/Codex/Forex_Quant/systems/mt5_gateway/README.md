# MT5 Gateway

The MT5 Gateway is the only system allowed to import or call the `MetaTrader5` Python package.

It provides:

- terminal/account status
- dynamic symbols from `symbols_get()`
- backend-owned timeframe mapping
- latest tick data
- historical OHLCV rates normalized to Quanta rows
- WebSocket tick streaming

Safety rules:

- no `order_send` wrapper
- no real-money execution
- no passwords or secrets stored
- all MT5 calls are serialized with a global lock
- if MT5 or the terminal is unavailable, routes return clean unavailable responses

