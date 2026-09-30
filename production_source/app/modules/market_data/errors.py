"""Expected market-data failures."""

class MarketDataError(Exception):
    pass

class UnsupportedTimeframeError(MarketDataError):
    pass

class MarketDataResponseError(MarketDataError):
    pass

class InsufficientClosedCandlesError(MarketDataError):
    pass

class MarketDataStaleError(MarketDataError):
    pass
