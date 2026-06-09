# MarketRegimeBot Guardrails Authority

This document is the central repo-owned safety authority for future Codex,
Claude, and human-assisted development prompts in MarketRegimeBot.

The guardrails are informational and policy-oriented. They do not enable broker
access, order execution, scheduler activation, Telegram execution, live trading,
or automatic money movement.

MarketRegimeBot is a read-only market regime analysis service. It classifies
market conditions and produces advisory regime signals. It is never an execution
engine, broker client, trading bot, portfolio manager, or scheduler authority.

## Permanent Forbidden Areas

The following areas are permanently forbidden unless a human explicitly opens a
separate reviewed implementation task with written approval:

- Broker imports or broker connections.
- IBKR or TWS imports, configuration, or integration changes.
- Order placement or order routing.
- Live trading behavior.
- Trading decision logic that affects real or simulated execution.
- Scheduler activation or scheduler behavior changes.
- Telegram execution or Telegram runtime behavior changes.
- Credential access, credential changes, or credential discovery.
- `.env` access or `.env` changes.
- Automatic money movement.

## Allowed Safe Work

The following work is allowed when it remains inert, reporting-only, and covered
by validation where appropriate:

- Runtime status JSON.
- Autocycle status JSON.
- Cycle history JSON.
- Reports.
- Schemas.
- Validators.
- Tests.
- Documentation.
- Read-only analytics.

Allowed work may define file formats, validate metadata, or write explicitly safe
status files only when the implementation is scoped to regime analysis reporting
and does not alter scheduler, execution, broker, Telegram, or trading logic.

## Human Approval Requirements

Commits and pushes require human approval. Autonomous agents may prepare diffs,
run tests, and report status, but must not commit or push unless the current user
message explicitly requests it.

Any future change that could affect broker access, order execution, scheduler
behavior, Telegram runtime behavior, TWS/IBKR integration, credentials, `.env`,
live trading, or money movement requires separate human review and approval.

## Broker, Order, And Trading Restrictions

MarketRegimeBot must not add broker imports, broker calls, order placement,
order mutation, order cancellation, or live-trading paths as part of
documentation, schema, validator, test, reporting, metadata, or read-only
analytics work.

Regime classification logic must not be connected to any execution path.
Regime outputs are advisory signals only and must never influence order
placement, capital allocation sizing, or live trading decisions.

## Regime Advisory Boundary

All regime outputs are:
- Informational only.
- Not binding on any trading system.
- Not capable of initiating orders, moving capital, or modifying positions.

No future autocycle, documentation, schema, or test task may change this
advisory boundary without separate human review and explicit written approval.

## Runtime Persistence Policy

Runtime persistence is allowed only for inert status metadata such as runtime
status JSON, autocycle status JSON, cycle history JSON, reports, schemas,
validators, tests, and documentation.

Runtime persistence must not activate a scheduler, create a background service,
change Telegram runtime behavior, connect to a broker, access credentials, read
or write `.env`, place orders, alter trading decisions, or move money.

When there is uncertainty, stop before implementation and document the blocker.
