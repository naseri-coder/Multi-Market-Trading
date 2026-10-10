# NASERI MARKETS A4 — Public Bot / Private Engine Boundary

**Scope:** source-code-only public A4 module, not a live service. The user wants
the generic bot to be public and reusable by anyone, while private NYFR logic
remains accessible only in a separate private GitHub repository.

## Repository ownership

- **PUBLIC:** `naseri-coder/Multi-Market-Trading` — generic, reusable signal
  publisher, market-data adapters, risk/identity contracts, SQLite outbox
  and independent analytics.
- **PRIVATE:** `naseri-coder/NY-First-Reversal` — strategy decision engine,
  original NY session interpretation, and private decision-to-envelope code.

## Independent public bot

- `naseri_markets.public_signal_bot.PublicSignalBot` consumes standardized
  `SignalIntent`, `EngineRegistry`, `ChannelRoute`, and a
  `PrivateChannelTransport`. No import of private NYFR source is permitted.
- `TelegramPrivateChannel` uses the official Telegram Bot API
  `getMe`/`getChat`/`getChatMember` to verify a channel without a public
  username and the bot's right to post. Delivery is disabled by default.
- Transport uses an operator-injected token. No credential, broker account,
  real channel ID, local market data or strategy settings are committed.
- An external verified **forward-live** feed attestation is required;
  caller-supplied boolean alone is NOT independent authentication of a
  proprietary engine, nor proof of source licensing or market-data quality.
- Publication is transactionally claimed before one send attempt.
  Unknown Telegram delivery means **manual reconciliation; never retry
  blindly after an ambiguous network response**.
- `naseri_markets.mt5_readonly_bridge` optionally emits sanitized quotes
  from an already-authorized local MetaTrader5 terminal. It does not
  call any order function and cannot produce a NYFR signal by itself.

## Licensing principle

Everyone may read, fork, modify and run the generic public bot according to
its repository licence. This does not distribute any NYFR source. GitHub
private collaborator permissions control who can access the private strategy.

Users who only receive private-channel signals do not need repository access.
A future source/binary distribution or licensed MT5 execution client would
require an independently authorized, signed, revocable entitlement service.
There is no heavyweight license server in A4.

## Exact limitations

This is not wired into the frozen `production_source` Docker image,
`app.main` entrypoint, or release v0.3.2 runtime. These public modules are
code-reviewable development libraries; no server, BotFather, MT5 terminal,
broker, channel or Telegram message was used during creation.

**Neither an offline unit test nor a successfully merged PR proves an
end-to-end live Telegram publication or actual trading profitability.**
