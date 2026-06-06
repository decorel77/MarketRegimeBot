# Current State

## MarketRegimeBot Skeleton - 2026-06-06

Status: SKELETON_ONLY / SAFE_DRY_RUN

MarketRegimeBot is a new separate NOVA ecosystem project for future market
regime detection. It currently emits only an UNKNOWN regime with confidence 0.

Current behavior:
- Produces a safe dry-run regime result.
- Writes only `data/system/result_snapshot.json` inside this project.
- Does not read market data yet.
- Does not export allocations or modify other NOVA repositories.

Safety lock:
- No broker execution.
- No order placement.
- No live trading.
- No money movement.
- No allocation export.
- No writes to other NOVA repositories.

