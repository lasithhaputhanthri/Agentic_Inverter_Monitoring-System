# IoT Incident Response Demo Walkthrough

This document outlines the standard 2-minute live demonstration of the multi-agent incident response system on a simulated solar inverter fleet. If running offline or without an active MQTT broker, refer to the fallback transcript at [docs/demo/fallback_demo_recording.txt](file:///f:/New%20Projects/Inverter_Monitoring_AI/docs/demo/fallback_demo_recording.txt).

---

## Prerequisites & Setup

Ensure dependencies are installed and the local environment is configured:

```bash
# 1. Install dependencies
make install

# 2. Start MQTT broker
docker compose up -d mosquitto
```

---

## 2-Minute Demo Script

### Step 1: Start Inverter Fleet Simulation (00:00 - 00:20)
Start the 20-inverter telemetry simulation:
```bash
python -m simulator.runner --fleet 20 --interval 5.0
```
*Expected Output:*
```text
[INFO] simulator: Initialized fleet of 20 commercial solar inverters (INV-01 to INV-20).
[INFO] simulator: Publishing synthetic irradiance & electrical telemetry to 'inverters/+/telemetry'.
```

### Step 2: Inject Overheating Fault on INV-01 (00:20 - 00:40)
Trigger an abnormal thermal elevation on device `INV-01`:
```bash
python -m simulator.inject --device INV-01 --fault overheating --duration 300
```
*Expected Output:*
```text
[INFO] fault_injector: Injected 'overheating' (+25.0°C thermal offset) on INV-01 for 300 seconds.
```

### Step 3: Deterministic Monitor Alert (00:40 - 01:00)
The non-LLM statistical baseline monitor evaluates published telemetry against physical irradiance expectations:
*Telemetry Observed:* Active power 4.2 kW, Ambient 25.0°C, Expected Inverter Temp 51.5°C, Observed Inverter Temp 76.5°C.
*Alert Generated:*
```json
{
  "alert_id": "alt-01j9a8b7c6d5e4f3a2b1",
  "device_id": "INV-01",
  "rule_id": "temp_high_for_power",
  "severity": "CRITICAL",
  "timestamp": "2026-06-01T14:30:15Z",
  "metrics": {
    "observed_temp_c": 76.5,
    "expected_temp_c": 51.5,
    "active_power_w": 4200.0
  }
}
```

### Step 4: Diagnosis & Remediation Reasoning (01:00 - 01:20)
1. **DiagnosisAgent** parses passive alert data inside XML boundary:
   - Root Cause: `overheating`
   - Confidence: `0.94`
   - Evidence: `"Core heatsink temperature 76.5°C exceeds thermal baseline by 25.0°C under 4.2 kW active load"`
2. **RemediationAgent** evaluates allowed action set and generates proposal:
   - Proposal ID: `prop-882194`
   - Target Device: `INV-01`
   - Action: `reduce_load`
   - Justification: `"Curtail active inverter power by 50% to mitigate thermal runaway risk until heatsink stabilizes."`

### Step 5: Operator Approval Gate (01:20 - 01:40)
The workflow graph enters `await_approval` and holds execution until authenticated operator review.
```bash
# Operator inspects pending approval
curl -s http://127.0.0.1:8000/api/approvals/pending \
  -H "X-API-Key: test_operator_key"

# Operator approves proposal
curl -X POST http://127.0.0.1:8000/api/incidents/inc-01j9a8b7c6d5e4f3a2b1/approve \
  -H "X-API-Key: test_operator_key" \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "operator_id": "lead_operator_01", "rationale": "Thermal rise confirmed via telemetry baseline."}'
```

### Step 6: Sandboxed Execution & Audit Log Verification (01:40 - 01:50)
1. The **Executor** modifies simulated inverter state (lowering power target to 50%).
2. The change is verified in simulated telemetry (temperature cools to 54.2°C).
3. The event is recorded in the append-only audit repository:
```bash
curl -s http://127.0.0.1:8000/api/audit/inc-01j9a8b7c6d5e4f3a2b1 \
  -H "X-API-Key: test_operator_key"
```
*Audit Records:*
- `alert_raised` -> `diagnosis_made` -> `proposal_made` -> `approval_requested` -> `approved` -> `executed`

### Step 7: Harm Interception Demonstration (Rejected Proposal) (01:50 - 02:00)
1. A secondary fault `grid_sag` is triggered on `INV-02`.
2. An unsafe proposal (`reset_relay`) is blocked before execution:
   - **Policy Engine**: Rejects action: `reset_relay` is forbidden for cause `grid_sag` (CRITICAL harm: reclosing relay during grid instability causes reverse-power backfeed).
   - **Operator Gate**: Marked rejected with rationale `"Grid sag requires grid stabilization before contactor closure."`
   - Simulator state remains untouched.

---

## Fallback Recording Reference
When a live broker or Python runtime is unavailable, review the pre-recorded demonstration execution transcript:
- [docs/demo/fallback_demo_recording.txt](file:///f:/New%20Projects/Inverter_Monitoring_AI/docs/demo/fallback_demo_recording.txt)
- [docs/demo/phase5_audit.txt](file:///f:/New%20Projects/Inverter_Monitoring_AI/docs/demo/phase5_audit.txt)
