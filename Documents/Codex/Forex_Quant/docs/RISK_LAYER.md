# Risk Layer

Risk approval combines old evidence and present conditions.

Old evidence is a historical trust profile: sample size, profit factor, and expectancy. Present evidence is current spread, data quality, drawdown, open trades, correlation exposure, news lock, and kill-switch status.

In this phase, strategies are not approved by history, so position sizing applies a large trust reduction. A good signal can still be rejected when spread, funded rules, data quality, or kill-switch rules fail.

Safety behavior:

- Wide spread blocks entries.
- Daily loss near the lock threshold blocks entries.
- Total drawdown beyond the limit blocks entries.
- News lock blocks entries by default.
- Manual kill switch and critical data quality are hard blocks.
- No risk code places broker orders.

