
# Final patch summary

## Critical fix
After:
    imported = await integration.import_signal(command)

Add fail closed behavior:
    if not imported.created:
        return without Telegram publish

Reason:
Existing signal must not be delivered again when a new candidate is duplicate or opposite.

## Runtime protection
Expected:
LONG active -> SHORT candidate = BLOCKED
SHORT active -> LONG candidate = BLOCKED
Duplicate active signal = BLOCKED
Closed signal -> new signal allowed
