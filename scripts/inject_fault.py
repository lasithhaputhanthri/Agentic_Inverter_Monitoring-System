"""CLI tool to inject a simulated fault and trigger live agent diagnosis and remediation.

Purpose: Demonstrates the multi-agent incident response pipeline on demand:
         - Simulates an out-of-spec operational anomaly.
         - Generates a deterministic alert matching physical monitoring baselines.
         - Calls DiagnosisAgent (using Google Gemini if LLM_PROVIDER=gemini, or Mock if mock).
         - Calls RemediationAgent to formulate a safe corrective proposal.
         - Verifies proposal against PolicyEngine guardrails.
         - Commits the alert and proposal into the database so it appears live on the dashboard.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from backend.agents.diagnosis import DiagnosisAgent
from backend.agents.llm_client import create_llm_client
from backend.agents.remediation import RemediationAgent
from backend.common.config import load_settings
from backend.executor.policy import PolicyEngine
from backend.monitor.models import Alert, AlertSeverity, MonitorRule
from backend.storage.database import get_engine, get_session_factory, init_db
from backend.storage.models import AlertRecord, AuditEventRecord, DiagnosisRecord, ProposalRecord
from backend.storage.repositories import AlertRepository, AuditEventRepository, IncidentRepository
from dotenv import load_dotenv

load_dotenv()


FAULT_PRESETS: dict[str, dict[str, Any]] = {
    "overheating": {
        "rule": MonitorRule.TEMP_HIGH_FOR_POWER,
        "severity": AlertSeverity.CRITICAL,
        "observed": "78.5 C",
        "threshold": "52.0 C",
        "message": "Inverter heatsink temperature 78.5 C exceeds expected thermal curve (52.0 C) under 4.2 kW active load",
        "telemetry": [
            {
                "ac_power_w": 4200.0,
                "dc_voltage_v": 580.0,
                "grid_voltage_v": 230.0,
                "temperature_c": 78.5,
                "relay_state": "closed",
            }
        ],
    },
    "grid_sag": {
        "rule": MonitorRule.GRID_VOLTAGE_LOW,
        "severity": AlertSeverity.CRITICAL,
        "observed": "188.4 V",
        "threshold": "207.0 V",
        "message": "Grid AC voltage dropped to 188.4 V, violating minimum threshold 207.0 V",
        "telemetry": [
            {
                "ac_power_w": 2800.0,
                "dc_voltage_v": 520.0,
                "grid_voltage_v": 188.4,
                "temperature_c": 44.0,
                "relay_state": "closed",
            }
        ],
    },
    "stuck_relay": {
        "rule": MonitorRule.RELAY_MISMATCH,
        "severity": AlertSeverity.CRITICAL,
        "observed": "open (3200.0W)",
        "threshold": "200.0 W",
        "message": "AC relay reports OPEN while active power remains high (3200.0 W), indicating welded contacts",
        "telemetry": [
            {
                "ac_power_w": 3200.0,
                "dc_voltage_v": 560.0,
                "grid_voltage_v": 230.0,
                "temperature_c": 49.2,
                "relay_state": "open",
            }
        ],
    },
    "comm_dropout": {
        "rule": MonitorRule.DEVICE_SILENT,
        "severity": AlertSeverity.WARNING,
        "observed": "85.0 s",
        "threshold": "60.0 s",
        "message": "No telemetry packets received for 85.0 seconds (timeout threshold: 60.0 s)",
        "telemetry": [],
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inject a simulated fault and trigger live AI incident response."
    )
    parser.add_argument(
        "--device",
        default="INV-01",
        help="Target inverter device ID (e.g. INV-01, INV-05). Default: INV-01",
    )
    parser.add_argument(
        "--fault",
        choices=list(FAULT_PRESETS.keys()),
        default="overheating",
        help="Type of fault to inject (overheating, grid_sag, stuck_relay, comm_dropout). Default: overheating",
    )
    args = parser.parse_args()

    preset = FAULT_PRESETS[args.fault]
    device_id = args.device.upper()
    now = datetime.now(UTC)

    print("=" * 70)
    print("⚡ SOLAR INVERTER FAULT INJECTION & MULTI-AGENT RESPONSE")
    print("=" * 70)
    print(f"Target Device:  {device_id}")
    print(f"Fault Category: {args.fault}")
    print(f"Trigger Rule:   {preset['rule'].value}")
    print(f"Observed Value: {preset['observed']} (Threshold: {preset['threshold']})")
    print("-" * 70)

    # 1. Database Setup
    settings = load_settings(enforce_secrets=False)
    engine = get_engine()
    init_db(engine)
    session = get_session_factory(engine)()

    alert_repo = AlertRepository(session)
    incident_repo = IncidentRepository(session)
    audit_repo = AuditEventRepository(session)

    # 2. Record Deterministic Monitor Alert
    alt_uuid = str(uuid.uuid4())
    alert = Alert.create(
        device_id=device_id,
        ts=now,
        rule=preset["rule"],
        severity=preset["severity"],
        observed=float(preset["observed"].split()[0]),
        threshold=float(preset["threshold"].split()[0]),
    )

    alert_record = AlertRecord(
        alert_id=alt_uuid,
        device_id=device_id,
        ts=now,
        rule=preset["rule"].value,
        severity=preset["severity"].value,
        observed=preset["observed"],
        threshold=preset["threshold"],
        message=preset["message"],
    )
    alert_repo.create_alert(alert_record)

    audit_repo.record_event(
        AuditEventRecord(
            event_id=str(uuid.uuid4()),
            event_type="alert_raised",
            payload_json=json.dumps(
                {
                    "alert_id": alt_uuid,
                    "device_id": device_id,
                    "rule": preset["rule"].value,
                    "severity": preset["severity"].value,
                    "observed": preset["observed"],
                }
            ),
        )
    )
    print(f"✅ Step 1: Monitor raised alert: {alt_uuid[:8]}...")

    # 3. Instantiate LLM Client (Gemini or Mock based on .env)
    provider_name = settings.llm_provider.lower().strip()
    model_name = settings.llm_model
    print(
        f"\n🤖 Step 2: Querying DiagnosisAgent ({provider_name.upper()} | Model: {model_name})..."
    )

    client = create_llm_client(settings)
    diag_agent = DiagnosisAgent(client=client, model_name=model_name)
    rem_agent = RemediationAgent(client=client, model_name=model_name)

    try:
        diagnosis = diag_agent.diagnose(alert, telemetry=preset["telemetry"])
    except Exception as exc:
        print(f"❌ Diagnosis failed: {exc}")
        return

    print(f"   Root Cause:  {diagnosis.cause}")
    print(f"   Confidence:  {diagnosis.confidence * 100:.1f}%")
    print("   Evidence:")
    for ev in diagnosis.evidence:
        print(f"     • {ev}")

    diag_uuid = str(uuid.uuid4())
    diag_record = DiagnosisRecord(
        diagnosis_id=diag_uuid,
        alert_id=alt_uuid,
        device_id=device_id,
        cause=str(diagnosis.cause),
        confidence=diagnosis.confidence,
        evidence_json=json.dumps(diagnosis.evidence),
        prompt_version=diagnosis.prompt_version,
        model=diagnosis.model,
        created_at=now,
    )
    incident_repo.create_diagnosis(diag_record)

    audit_repo.record_event(
        AuditEventRecord(
            event_id=str(uuid.uuid4()),
            event_type="diagnosis_made",
            payload_json=json.dumps(
                {
                    "diagnosis_id": diag_uuid,
                    "cause": str(diagnosis.cause),
                    "confidence": diagnosis.confidence,
                    "evidence": diagnosis.evidence,
                }
            ),
        )
    )

    # 4. Formulate Remediation Proposal
    print(f"\n🛡️  Step 3: Querying RemediationAgent ({provider_name.upper()})...")
    try:
        proposal = rem_agent.propose(alert, diagnosis)
    except Exception as exc:
        print(f"❌ Remediation proposal failed: {exc}")
        return

    print(f"   Proposed Action: {proposal.action}")
    print(f"   Justification:   {proposal.justification}")

    # 5. Deterministic Policy Engine Safety Verification
    policy = PolicyEngine.load("config/policy.yaml")
    is_allowed = policy.is_allowed(str(diagnosis.cause), str(proposal.action))
    print(
        f"   Policy Gate:     {'✅ ALLOWED' if is_allowed else '❌ BLOCKED BY POLICY GUARDRAILS'}"
    )

    prop_uuid = str(proposal.proposal_id)
    prop_record = ProposalRecord(
        proposal_id=prop_uuid,
        diagnosis_id=diag_uuid,
        alert_id=alt_uuid,
        device_id=device_id,
        action=str(proposal.action),
        justification=proposal.justification,
        status="pending" if is_allowed else "blocked",
        created_at=now,
    )
    incident_repo.create_proposal(prop_record)

    audit_repo.record_event(
        AuditEventRecord(
            event_id=str(uuid.uuid4()),
            event_type="proposal_made",
            payload_json=json.dumps(
                {
                    "proposal_id": prop_uuid,
                    "action": str(proposal.action),
                    "justification": proposal.justification,
                    "policy_allowed": is_allowed,
                }
            ),
        )
    )

    print("\n" + "=" * 70)
    print("🎉 SUCCESS! Live Incident Dispatched to Dashboard")
    print("=" * 70)
    print("Next Steps:")
    print("1. Open your Streamlit Dashboard: http://localhost:8501")
    print("2. Click on the 'Alerts' tab to view the active alarm.")
    print("3. Click on the 'Remediation Proposals' tab to inspect Gemini's reasoning.")
    print("4. Click [Approve] or [Reject] to complete the human-in-the-loop workflow!")
    print("5. Check 'Incident Timeline' to review the tamper-evident audit trail.")
    print("=" * 70)


if __name__ == "__main__":
    main()
