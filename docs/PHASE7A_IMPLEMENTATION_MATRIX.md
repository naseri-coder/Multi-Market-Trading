# Phase 7A Implementation Matrix

| Rule | Implemented | Role | Reason |
|---|---:|---|---|
| BR-010 | Yes | deterministic primitive | explicit OHLC relation |
| BR-011 | Yes | deterministic primitive | explicit OHLC relation |
| BR-012 | Yes | source configuration metadata | EMA length explicitly 20 |
| BR-015 | Yes, conditional | context classifier | requires pre-resolved trend |
| BR-017 | Yes, conditional | trend-state mapping | flip algorithm remains unresolved |
| BR-019 | Yes | heuristic metadata | never calibrated as 0.80 probability |
| BR-020 | Yes | policy guard | volume not required |
| BR-027 | Yes | validation guard | pattern alone insufficient |
| BR-029 | Yes | heuristic metadata | never calibrated as 0.80 probability |
| BR-030 | Yes | heuristic metadata | never calibrated as 0.80 probability |
| BR-035 | Yes | validation guard | indicators secondary to bars |
| BR-001/002/003/004/005/006/007/008/016/023/024/025/026/031/032/033/034 | Not autonomous | blocked/qualitative | unresolved deterministic thresholds or upstream classifiers |
| BR-036/037 | Not used | Forex-specific | outside current crypto engine scope |
