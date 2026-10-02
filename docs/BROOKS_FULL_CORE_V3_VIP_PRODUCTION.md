# Brooks Full Core v3 — VIP Production Activation

This phase changes the runtime from PAPER private-test mode to LIVE VIP publication.

Safety contract:
- Market data remains public read-only exchange data.
- No exchange order execution is introduced.
- LIVE signals use publication_scope=VIP.
- LIVE signals count toward production performance.
- Telegram delivery uses durable signal_deliveries state with TELEGRAM_VIP.
- PAPER and LIVE are mutually exclusive.
- A persistent BROOKS_LIVE_CUTOVER_AT watermark prevents any snapshot already
  closed at activation time from being republished as LIVE.
- Existing PAPER rows and deliveries are not rewritten.
- The VIP channel is Signal VIP (-1003825225083).
