# MT-A1: offline MQ4/MQ5/EX5 artifact preflight

**Status: NONPRODUCTION REVIEW ONLY — NO MetaTrader execution or integration claimed.**

Existing MT5 DEMO read-only observation modules remain unchanged. MT4
does not have a native Python SDK in this project. MQL4, MQL5 and EX5
are NOT Python/JS/TS/WASM Core API artifacts and may not run through
RUNTIME-A1. RUNTIME-A6 continues to deny every Worker launch.

## Implemented contract

The review-only function in naseri_markets/mt_a1_offline_artifact_preflight.py
accepts three precise local artifact classes:

- .mq4: MT4 MQL4 source, decoded as UTF-8, UTF-8 BOM, or UTF-16 LE/BE BOM
- .mq5: MT5 MQL5 source, with the same strict text-decoding rules
- .ex5: MT5 proprietary compiled bytes, treated as opaque data

EX5's actual format, compilation provenance and compatibility cannot
be verified from filename extension or SHA256. No EX4, DLL or EXE
support is included. Text decoding is NOT MQL compilation, static
security audit, sandbox validation or proof of a safe trading strategy.

Requires an operator-preapproved lowercase SHA256, absolute nonsymlink
regular file with no hardlinks, bounded size (8 MiB source, 32 MiB EX5)
and stable file identity, size and timestamps across the read.
It retains only digest, file size, source line count/encoding (when
applicable), and operator-declared market, symbol, timeframe and
provider label — never the source bytes or account credentials.

MMT_NONPRODUCTION=1 is required, MMT_PRODUCTION=1 is forbidden, and
operator_ack=True is mandatory. No user file is executed, compiled,
installed, sent over the network, or persisted by this function.

## Standard timeframe identity mapping

| MetaTrader | DATA-A1 | MT4 | MT5 |
| --- | --- | --- | --- |
| M1 | 1m | yes | yes |
| M5 | 5m | yes | yes |
| M15 | 15m | yes | yes |
| M30 | 30m | yes | yes |
| H1 | 1h | yes | yes |
| H4 | 4h | yes | yes |
| H12 | 12h | no standard native H12 | yes |
| D1 | 1d | yes | yes |

This mapping is an operator-declared compatibility contract only,
not proof of broker data availability, timezone, session calendar,
spread, fill behavior, trade profitability or actual MT4/MT5 connectivity.

## Operator-reviewed example

On a disposable nonproduction host with MMT_NONPRODUCTION=1:

~~~python
from pathlib import Path
from naseri_markets.contracts import Market
from naseri_markets.mt_a1_offline_artifact_preflight import (
    MetaTraderPlatform, review_metatrader_artifact,
)

result = review_metatrader_artifact(
    Path("/absolute/path/to/strategy.mq5"),
    expected_sha256="PREAPPROVED_LOWERCASE_64_HEX_DIGEST",
    platform=MetaTraderPlatform.MT5,
    market=Market.FOREX,
    symbol="EURUSD",
    timeframe="M15",
    provider_claim="operator_declared_demo",
    operator_ack=True,
)
~~~

Real SHA256 must replace the example placeholder.
The report always declares compiled=False, EX5 format verified=False,
account/broker authenticated=False, terminal connected=False, live
data observed=False, PAPER strategy executed=False, broker order sent=False,
Telegram sent=False and Worker execution authorized=False.

## Release blockers

1. Operator-designated disposable Windows MT4/MT5 terminal and explicit
   DEMO account identity: NOT AVAILABLE in this review. The existing MT5
   opt-in read-only demo adapter is separate and not executed in this stage.
2. Trusted vendor MetaEditor toolchain for source compile and artifact
   format/provenance attestation: NOT AVAILABLE.
3. EX5 cannot be safely treated as MQL source or run via A1. No EX5
   disassembly, dynamic analysis or unsafe execution is undertaken.
4. Real Point-in-Time broker history, tick/bar source quality, trade
   contract specs, commissions, swap, spread, slippage and session
   calendar must be validated separately before any meaningful test.
5. Independent runtime isolation evidence and authorization are needed
   before considering any future execution. A6 still denies launch.

Mock-only CI fixtures provide actual local MQ4/MQ5 text and synthetic
opaque EX5 bytes, not genuine compiled vendor EX5. Test boundaries cover
integrity, file identity, timeframe, decoding, operator approval and
denial of process/network use, plus regression of MT5 DEMO read-only,
DATA→RUNTIME inert wire, and A6.

**Verdict: MT_A1_ARTIFACT_REVIEW_PREPARED_TERMINAL_CONNECTION_NOT_PROVEN.**
