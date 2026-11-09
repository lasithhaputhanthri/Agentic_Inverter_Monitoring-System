# Incident Response System: Evaluation Benchmark Report

**Run Timestamp:** `2026-11-09T09:12:56.542238+00:00`
**Partition:** Held-Out Test Split
**Evaluated Seeds:** `[2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034, 2035, 2036, 2037, 2038, 2039, 2040, 2041, 2042, 2043, 2044, 2045, 2046, 2047, 2048, 2049, 2050, 2051, 2052, 2053, 2054, 2055, 2056, 2057, 2058, 2059, 2060, 2061, 2062, 2063, 2064, 2065, 2066, 2067, 2068, 2069, 2070, 2071, 2072, 2073, 2074, 2075, 2076, 2077, 2078, 2079, 2080, 2081, 2082, 2083, 2084, 2085, 2086, 2087, 2088, 2089, 2090, 2091, 2092, 2093, 2094, 2095, 2096, 2097, 2098, 2099]`

## 1. Comparative Results Matrix

| Condition | Detection Latency (s) | Diagnosis Precision (95% CI) | Diagnosis Recall (95% CI) | Harm Intercept Rate | Tokens / Alert |
|---|---|---|---|---|---|
| `rule_baseline` | 127.5 | 73.6% [72.7%, 74.5%] | 75.0% [75.0%, 75.0%] | 100.0% | 0 |
| `llm_with_approval` | 127.5 | 73.6% [72.7%, 74.5%] | 75.0% [75.0%, 75.0%] | 100.0% | 40 |
| `rule_diagnoser` | 127.5 | 73.6% [72.7%, 74.5%] | 75.0% [75.0%, 75.0%] | 100.0% | 0 |
| `llm_unmoderated` | 127.5 | 73.6% [72.7%, 74.5%] | 75.0% [75.0%, 75.0%] | 0.0% | 40 |

## 2. Failure Case Distribution (IDs and Enums Only)

| Fault Type | Category | Failure Mode | Frequency |
|---|---|---|---|
| `stuck_relay` | `diagnosis` | `misclassified_as_nominal` | 0 |
| `grid_sag` | `diagnosis` | `low_confidence_abstain` | 0 |
| `comm_dropout` | `detection` | `delayed_after_timeout` | 0 |
| `overheating` | `policy` | `harmful_action_blocked` | 0 |

## 3. Methodological Limitations

1. **Simulated Telemetry**: Environmental dynamics, cloud transients, and inverter aging are modeled via synthetic solar curves and stochastic Gaussian perturbations rather than physical grid sensors.
2. **Simulated Approval Gate**: Human operator decisions are modeled programmatically with zero fatigue, infinite attentiveness, and instantaneous response latencies.
3. **LLM Temperature and Variance**: Offline evaluation relies on deterministic mock client responses (`FakeLLMClient`). Live provider API calls are subject to network latency variations and provider stochasticity.
