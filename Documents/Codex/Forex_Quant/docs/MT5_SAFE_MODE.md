# MT5 Safe Mode

MT5 integration is intentionally not active in this build.

When added, it must start in demo mode and refuse real orders unless all of these are true:

- `live_trading_enabled: true`
- `allow_live_trading: true`
- `allow_real_orders: true`
- funded rules pass
- kill switch is clear
- strategy is `live_approved`
- historical trust profile is approved

Credentials and terminal paths must come from environment variables or ignored local config files, never from committed code.

