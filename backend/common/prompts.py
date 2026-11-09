"""CLI interaction helpers for human-in-the-loop decisions.

Purpose: Presents structured incident context to operators and collects approval decisions.
Inputs: ActionProposal, DiagnosisResult, Alert duck-typed objects, and optional operator name or input stream.
Outputs: Tuple of (decision_string ['approve'/'reject'], optional reason string, operator identifier).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any


def format_incident_card(
    proposal: Any,
    diagnosis: Any,
    alert: Any,
) -> str:
    """Format structured incident details into a human-readable CLI summary."""
    device_id = getattr(alert, "device_id", str(alert))
    rule_val = getattr(getattr(alert, "rule", None), "value", str(getattr(alert, "rule", "")))
    severity_val = getattr(
        getattr(alert, "severity", None), "value", str(getattr(alert, "severity", ""))
    )
    ts_val = getattr(
        getattr(alert, "ts", None), "isoformat", lambda: str(getattr(alert, "ts", ""))
    )()
    obs_val = getattr(alert, "observed", "")
    thresh_val = getattr(alert, "threshold", "")

    cause_val = getattr(
        getattr(diagnosis, "cause", None), "value", str(getattr(diagnosis, "cause", ""))
    )
    conf_val = getattr(diagnosis, "confidence", 1.0)
    ev_val = getattr(diagnosis, "evidence", [])
    ev_str = ", ".join(str(e) for e in ev_val) if isinstance(ev_val, list) else str(ev_val)

    act_val = getattr(
        getattr(proposal, "action", None), "value", str(getattr(proposal, "action", ""))
    )
    just_val = getattr(proposal, "justification", "")

    lines = [
        "=" * 60,
        "INCIDENT APPROVAL REQUEST",
        "=" * 60,
        f"Device:        {device_id}",
        f"Alert Rule:    {rule_val} ({severity_val})",
        f"Timestamp:     {ts_val}",
        f"Observed:      {obs_val} (Threshold: {thresh_val})",
        "-" * 60,
        f"Diagnosed Cause: {cause_val} (Confidence: {conf_val:.0%})",
        f"Evidence:        {ev_str}",
        "-" * 60,
        f"Proposed Action: {act_val}",
        f"Justification:   {just_val}",
        "=" * 60,
    ]
    return "\n".join(lines)


def ask_decision(
    proposal: Any,
    diagnosis: Any,
    alert: Any,
    operator_name: str = "operator_admin",
    input_fn: Callable[[str], str] | None = None,
) -> tuple[str, str | None, str]:
    """Prompt operator on CLI for an approval decision with optional reason.

    Args:
        proposal: Action proposal under review.
        diagnosis: Supporting diagnostic finding.
        alert: Triggering monitor alert.
        operator_name: Name or ID of the human operator.
        input_fn: Optional input callable (for headless tests or custom streams).

    Returns:
        Tuple of (decision_string ['approve'/'reject'], optional reason string, operator identifier).
    """
    card = format_incident_card(proposal, diagnosis, alert)
    print(card, file=sys.stderr)

    ask = input_fn or input

    prompt_text = "Decision ([a]pprove / [r]eject): "
    resp = ask(prompt_text).strip().lower()

    if resp in ("a", "approve", "yes", "y"):
        decision = "approve"
    else:
        decision = "reject"

    reason: str | None = None
    if decision == "reject":
        reason_text = ask("Reason for rejection (optional): ").strip()
        reason = reason_text if reason_text else "Operator rejected via CLI"
    else:
        reason_text = ask("Approval note (optional): ").strip()
        reason = reason_text if reason_text else None

    return decision, reason, operator_name
