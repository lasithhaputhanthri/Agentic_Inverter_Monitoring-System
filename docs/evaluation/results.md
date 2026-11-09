# Incident Response System: Evaluation Benchmark Report

**Run Timestamp:** `2026-11-09T08:07:15.053492+00:00`
**Partition:** Tuning / Validation Split
**Evaluated Seeds:** `[1000, 1001, 1002, 1003, 1004]`

## 1. Comparative Results Matrix

| Condition | Detection Latency (s) | Diagnosis Precision (95% CI) | Diagnosis Recall (95% CI) | Harm Intercept Rate | Tokens / Alert |
|---|---|---|---|---|---|
| `rule_baseline` | 150.0 | 72.4% [68.3%, 78.9%] | 75.0% [75.0%, 75.0%] | 100.0% | 0 |
| `llm_with_approval` | 150.0 | 72.4% [68.3%, 78.9%] | 75.0% [75.0%, 75.0%] | 100.0% | 40 |
| `rule_diagnoser` | 150.0 | 72.4% [68.3%, 78.9%] | 75.0% [75.0%, 75.0%] | 100.0% | 0 |
| `llm_unmoderated` | 150.0 | 72.4% [68.3%, 78.9%] | 75.0% [75.0%, 75.0%] | 0.0% | 40 |

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
