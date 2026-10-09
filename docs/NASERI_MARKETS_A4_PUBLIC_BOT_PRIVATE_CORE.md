# NASERI MARKETS A4 — PUBLIC Bot / PRIVATE Strategy Core Split

## Ownership / visibility (2026-10-09)

- PUBLIC: \`naseri-coder/crypto-price-action\` — NASERI MARKETS platform,
  generic source code for the signal bot, quote transport, state machines,
  validation, analytics, and eventual Telegram delivery adapters.
- PRIVATE: \`naseri-coder/NY-First-Reversal\` — NY First-Reversal strategy
  logic, US30 session interpretation, strategy-specific settings, and private
  input-to-intent conversion. Public consumers CANNOT generate NYFR signals
  from the public bot code alone.

## Public API / behavior

- \`naseri_markets.public_signal_bot.PublicSignalBot\` consumes **only**
  \`SignalIntent\`, \`EngineRegistry\`, \`ChannelRoute\`, \`SignalLedger\` and a
  \`PrivateChannelTransport\`. It never imports \`r0_engine\`, \`NYFRPrivateCore\`,
  any private code, or any broker order API.
- Generic Telegram transport uses getMe/getChat/getChatMember for independent
  private channel and publisher-permission checks. It is **disabled by default**,
  and the bot token is injected by the operator at runtime, never stored.
- An ambiguous send means no blind retry after restart. Only a confirmed
  Telegram message_id permits a SENT acknowledgment.
- Historical/paper messages may not be misrepresented as real-time forward
  publication; stale signals and unauthenticated feeds are rejected.
- \`naseri_markets.mt5_readonly_bridge\` is an optional read-only price source;
  NO strategy parameters or trade execution functions are present.
- A **public bot** means anyone can inspect/modify/run their copy of the bot.
  They still do not get the private NYFR strategy. The user retains control
  of who has GitHub collaborator access to the private core.

## Licensing without a heavyweight authority

For this research stage, private GitHub source access is the NYFR intellectual
property boundary. An approved operator may run the private strategy locally
or on a future controlled host and feed its signals to the public bot.

End users get **signal access only**, via a separately managed private Telegram
channel with manual membership/expiry. No public Python source licenses can
prevent someone from running their **own** generic signal bot; that is expected.

An execution-capable MT5 EA or distributing a private core binary is a separate
future stage requiring signed, short-lived entitlements and revocation. No
end-user executable license service is implemented here.

## Status / evidence limitations

This is a stacked development PR based on A3 #128, not deployed. A1–A3
are review branches, not on main. No broker feed or Telegram token has been
configured. In-process unit tests are not evidence of market profitability
or successful real Telegram publication.

**Do not copy any private source into this public repo, including Git history.**
