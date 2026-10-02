# Integration Phase 6 — Brooks Engine Adapter + Chart Renderer Boundary

Inventory confirmed that the bot does not contain a concrete Brooks strategy engine or a
chart renderer. This phase therefore does not fabricate Brooks rules.

Added:
- ActualBrooksStrategyEngine protocol
- BrooksEngineResult
- BrooksCoreAnalyzerAdapter
- deterministic source_signal_id
- strict snapshot id/hash propagation
- SignalChartRenderer protocol
- MatplotlibSignalChartRenderer
- PNG candlestick rendering with Entry/SL/TP overlays
- NO_SIGNAL path that skips rendering

Safety:
- no database migration
- PAPER remains disabled
- no background scanner
- no Telegram auto-publish
- no public/VIP activation
- no real orders

A reviewed concrete Brooks strategy implementation is still required before automated
trade decisions can be produced.
