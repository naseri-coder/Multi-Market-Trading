from pathlib import Path
import hashlib
import json
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.operations.trade_management import POLICY_VERSION
ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts/statistics_contract_v1.json"
CONTRACT_SHA = '0db6b0a436604010838cfcbefecffadcdd579e1b6ff75142930d9c0169c75fd5'
CONTRACT = json.loads(CONTRACT_PATH.read_text())
ENGINE = BrooksTrilogyFullCoreEngine.engine_version
RULES = BrooksTrilogyFullCoreEngine.rule_set_version
MGMT = POLICY_VERSION
CONFIGURATION = BrooksFullCorePolicy().configuration_version
RISK_SEMANTIC_MODEL = CONTRACT["risk_semantic_model"]
RUNNER_POLICY = CONTRACT["runner_policy"]
ARTIFACT_SCHEMA_VERSION = CONTRACT["artifact_schema_version"]
STAT = ORIG_STAT = CONTRACT["current_dataset_contract_id"]
MIN_N = 20
BOOTSTRAPS = 100000
EPS = 1e-15
Z95 = 1.959963984540054
SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "TRXUSDT", "HYPEUSDT", "ZECUSDT", "DOGEUSDT", "XMRUSDT")
TIMEFRAMES = ("15m", "1h")
COHORT_FIELDS = ("engine_version", "rule_set_version", "configuration_version", "exchange", "market_type", "management_version", "artifact_schema_version", "risk_semantic_model", "runner_policy", "statistics_contract_version")
def assert_contract():
    assert hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest() == CONTRACT_SHA
