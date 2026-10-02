Final wiring plan:

1) repository.py
   Add get_active_signal_context(symbol,timeframe)
   Query Signal joined with SignalAutomationMetadata
   Only status == OPEN.

2) signal_automation/service.py
   Before create_signal:
   - load active signal
   - run check_direction_conflict
   - stop duplicate/opposite creation

3) live_vip_runtime/service.py
   After import_signal:
   if imported.created is False:
       do not publish Telegram
       return SKIPPED_DUPLICATE
