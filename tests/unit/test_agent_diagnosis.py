"""Unit tests for the DiagnosisAgent.

Purpose: Verifies diagnosis inference, retries, quota ceilings, cache hits, and fallbacks.
Inputs: Alert instances, scripted FakeLLMClient responses, and mocked token quotas.
Outputs: Pytest assertions verifying diagnostic behavior.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from backend.agents.cache import AgentCache
from backend.agents.diagnosis import DiagnosisAgent
from backend.agents.llm_client import FakeLLMClient
from backend.agents.models import DiagnosisCause
from backend.agents.quota import QuotaTracker
from backend.common.errors import LLMQuotaExceededError
from backend.monitor.models import Alert, AlertSeverity, MonitorRule


def _make_alert(dev_id: str = "INV-01") -> Alert:
    return Alert.create(
        device_id=dev_id,
        ts=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC),
        rule=MonitorRule.TEMP_HIGH_FOR_POWER,
        severity=AlertSeverity.WARNING,
        observed=65.0,
        threshold=12.0,
    )


def test_diagnosis_agent_valid_response_first_attempt() -> None:
    """Acceptance test: Valid response is accepted on attempt 1 with exactly 1 call."""
    scripted = json.dumps(
        {
            "cause": "overheating",
            "confidence": 0.95,
            "evidence": ["Temperature is 65C (19C above expected)"],
        }
    )
    client = FakeLLMClient(scripted_responses=[scripted])
    agent = DiagnosisAgent(client=client)

    alert = _make_alert()
    res = agent.diagnose(alert)

    assert res.cause == DiagnosisCause.OVERHEATING
    assert res.confidence == 0.95
    assert client.call_count == 1
    assert agent.last_call_metadata["attempts"] == 1
    assert agent.last_call_metadata["status"] == "success"


def test_diagnosis_agent_retry_after_one_malformed_response() -> None:
    """Acceptance test: One malformed response followed by a valid one is accepted with 2 calls."""
    malformed = "NOT_VALID_JSON"
    valid = json.dumps(
        {
            "cause": "grid_sag",
            "confidence": 0.88,
            "evidence": ["Grid voltage measured at 195 V"],
        }
    )
    client = FakeLLMClient(scripted_responses=[malformed, valid])
    agent = DiagnosisAgent(client=client)

    alert = _make_alert()
    res = agent.diagnose(alert)

    assert res.cause == DiagnosisCause.GRID_SAG
    assert client.call_count == 2
    assert agent.last_call_metadata["attempts"] == 2
    assert agent.last_call_metadata["status"] == "success_after_retry"


def test_diagnosis_agent_fallback_to_unknown_after_two_failures() -> None:
    """Acceptance test: Two malformed responses produce 'unknown' and record schema_failure."""
    client = FakeLLMClient(scripted_responses=["BAD_1", "BAD_2"])
    agent = DiagnosisAgent(client=client)

    alert = _make_alert()
    res = agent.diagnose(alert)

    assert res.cause == DiagnosisCause.UNKNOWN
    assert res.confidence == 0.0
    assert client.call_count == 2
    assert agent.last_call_metadata["status"] == "schema_failure"


def test_diagnosis_agent_timeout_records_llm_unavailable() -> None:
    """Acceptance test: Timeout records llm_unavailable and falls back to unknown."""
    client = FakeLLMClient()
    client.simulate_timeout = True
    agent = DiagnosisAgent(client=client)

    alert = _make_alert()
    res = agent.diagnose(alert)

    assert res.cause == DiagnosisCause.UNKNOWN
    assert agent.last_call_metadata["status"] == "llm_unavailable"


def test_diagnosis_agent_quota_ceiling_blocks_call() -> None:
    """Acceptance test: At the daily limit, the fake client records zero calls."""
    quota = QuotaTracker(daily_call_limit=2)
    quota.daily_calls = 2  # Limit reached

    client = FakeLLMClient()
    agent = DiagnosisAgent(client=client, quota=quota)

    alert = _make_alert()
    with pytest.raises(LLMQuotaExceededError, match="Daily LLM call quota"):
        agent.diagnose(alert)

    assert client.call_count == 0


def test_diagnosis_agent_cache_hit_and_invalidation() -> None:
    """Acceptance test: Identical input reuses result. New prompt version invalidates it."""
    scripted = json.dumps({"cause": "overheating", "confidence": 0.9, "evidence": ["Temp high"]})
    client = FakeLLMClient(scripted_responses=[scripted])
    cache = AgentCache()
    agent1 = DiagnosisAgent(client=client, cache=cache, prompt_version="diagnosis_v1")

    alert = _make_alert()
    res1 = agent1.diagnose(alert)
    assert client.call_count == 1

    # Second call with same input reuses cached result without calling client
    res2 = agent1.diagnose(alert)
    assert client.call_count == 1
    assert res1.cause == res2.cause

    # Different prompt version invalidates cache
    client.queue_response(
        json.dumps({"cause": "overheating", "confidence": 0.92, "evidence": ["v2 temp high"]})
    )
    agent2 = DiagnosisAgent(client=client, cache=cache, prompt_version="diagnosis_v1")
    agent2.prompt_version = "diagnosis_v2"  # Version changed
    res3 = agent2.diagnose(alert)
    assert res3.cause == DiagnosisCause.OVERHEATING
    assert client.call_count == 2
