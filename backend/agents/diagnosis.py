"""Diagnosis agent for identifying root causes of inverter incidents.

Purpose: Analyzes incident alerts and telemetry with an LLM, enforcing strict schemas,
         input/output token budgets, retries, fallbacks, and output sanitization.
Inputs: Alert instance, recent device telemetry, and optional fleet snapshot.
Outputs: Validated, immutable DiagnosisResult.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from pydantic import ValidationError

from backend.agents.cache import AgentCache
from backend.agents.guard import scan_free_text
from backend.agents.llm_client import LLMClient
from backend.agents.models import DiagnosisCause, DiagnosisResult
from backend.agents.prompts import load_prompt
from backend.agents.quota import QuotaTracker, estimate_tokens
from backend.common.errors import LLMQuotaExceededError, LLMTimeoutError, LLMUnavailableError
from backend.common.logging import get_logger
from backend.monitor.models import Alert

logger = get_logger(__name__)

DIAGNOSIS_INPUT_TOKEN_CAP: int = 1500
DIAGNOSIS_OUTPUT_TOKEN_CAP: int = 300


def _escape_data(val: str) -> str:
    """Escape angle brackets so passive data cannot break out of XML delimiter blocks."""
    return val.replace("<", "&lt;").replace(">", "&gt;")


def _strip_json_fences(text: str) -> str:
    """Remove accidental markdown code fences if emitted by the model."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Find outer curly braces
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1].strip()
    return cleaned


class DiagnosisAgent:
    """Agent that diagnoses root cause of inverter incident alerts."""

    def __init__(
        self,
        client: LLMClient,
        cache: AgentCache | None = None,
        quota: QuotaTracker | None = None,
        prompt_version: str = "diagnosis_v1",
        model_name: str = "mock-model",
    ) -> None:
        self.client = client
        self.cache = cache or AgentCache()
        self.quota = quota or QuotaTracker()
        self.prompt_version = prompt_version
        self.model_name = model_name
        self.prompt_text, self.prompt_hash = load_prompt(f"{prompt_version}.txt")
        self.last_call_metadata: dict[str, Any] = {}

    def _build_prompt(
        self,
        alert: Alert,
        telemetry: list[dict[str, Any]] | None,
        fleet_snapshot: dict[str, dict[str, Any]] | None,
    ) -> str:
        """Construct delimited prompt while strictly honoring the input token ceiling."""
        alert_json = json.dumps(
            {
                "alert_id": str(alert.alert_id),
                "device_id": alert.device_id,
                "rule": alert.rule.value,
                "severity": alert.severity.value,
                "observed": alert.observed,
                "threshold": alert.threshold,
                "ts": alert.ts.isoformat(),
            },
            sort_keys=True,
        )
        escaped_alert = _escape_data(alert_json)

        base_prompt = f"{self.prompt_text}\n\n<alert>\n{escaped_alert}\n</alert>\n\n"

        base_tokens = estimate_tokens(base_prompt)
        if base_tokens >= DIAGNOSIS_INPUT_TOKEN_CAP:
            raise LLMQuotaExceededError(
                f"Base prompt ({base_tokens} tokens) exceeds input token ceiling ({DIAGNOSIS_INPUT_TOKEN_CAP})"
            )

        # Budget remaining for telemetry and fleet snapshot
        remaining_tokens = DIAGNOSIS_INPUT_TOKEN_CAP - base_tokens - 100

        # Add newest telemetry samples first until remaining budget is full
        selected_samples: list[dict[str, Any]] = []
        if telemetry:
            for sample in reversed(telemetry):
                sample_json = json.dumps(sample, sort_keys=True)
                sample_tokens = estimate_tokens(sample_json)
                if sample_tokens <= remaining_tokens:
                    selected_samples.insert(0, sample)
                    remaining_tokens -= sample_tokens
                else:
                    break

        telemetry_block = ""
        if selected_samples:
            escaped_telem = _escape_data(json.dumps(selected_samples, sort_keys=True))
            telemetry_block = f"<telemetry>\n{escaped_telem}\n</telemetry>\n\n"

        snapshot_block = ""
        if fleet_snapshot and remaining_tokens > 100:
            escaped_snap = _escape_data(json.dumps(fleet_snapshot, sort_keys=True))
            snapshot_tokens = estimate_tokens(escaped_snap)
            if snapshot_tokens <= remaining_tokens:
                snapshot_block = f"<fleet_snapshot>\n{escaped_snap}\n</fleet_snapshot>\n\n"

        full_prompt = f"{base_prompt}{telemetry_block}{snapshot_block}".strip()

        # Hard budget check: a call over budget is NEVER made
        if estimate_tokens(full_prompt) > DIAGNOSIS_INPUT_TOKEN_CAP:
            raise LLMQuotaExceededError("Assembled prompt exceeds input token ceiling")

        return full_prompt

    def diagnose(
        self,
        alert: Alert,
        telemetry: list[dict[str, Any]] | None = None,
        fleet_snapshot: dict[str, dict[str, Any]] | None = None,
    ) -> DiagnosisResult:
        """Diagnose root cause for an alert with quota enforcement, validation, and single retry."""
        # Check cache
        features = {
            "alert": alert.model_dump(mode="json"),
            "telemetry": telemetry or [],
            "snapshot": fleet_snapshot or {},
        }
        cached = self.cache.get(features, self.prompt_version, self.model_name)
        if cached is not None and isinstance(cached, DiagnosisResult):
            return cast(DiagnosisResult, cached)

        prompt = self._build_prompt(alert, telemetry, fleet_snapshot)

        # First attempt
        self.quota.check_call_quota()
        self.quota.record_call()

        try:
            resp = self.client.generate(
                prompt=prompt,
                max_tokens=DIAGNOSIS_OUTPUT_TOKEN_CAP,
                temperature=0.0,
            )
            result = self._parse_and_validate(resp.text, alert.device_id, resp.model)
            self.last_call_metadata = {
                "attempts": 1,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "model": resp.model,
                "latency_ms": resp.latency_ms,
                "status": "success",
            }
            self.cache.set(features, self.prompt_version, self.model_name, result)
            return result

        except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as exc:
            logger.warning(
                "[DiagnosisAgent] Attempt 1 failed validation: %s. Retrying once...", exc
            )

            # Retry once with error feedback
            self.quota.check_call_quota()
            self.quota.record_call()
            retry_prompt = (
                f"{prompt}\n\n"
                f"<error>\n"
                f"Prior response failed validation: {_escape_data(str(exc))}. "
                f"You must emit valid JSON matching the schema exactly.\n"
                f"</error>"
            )

            try:
                resp2 = self.client.generate(
                    prompt=retry_prompt,
                    max_tokens=DIAGNOSIS_OUTPUT_TOKEN_CAP,
                    temperature=0.0,
                )
                result2 = self._parse_and_validate(resp2.text, alert.device_id, resp2.model)
                self.last_call_metadata = {
                    "attempts": 2,
                    "input_tokens": resp.input_tokens + resp2.input_tokens,
                    "output_tokens": resp.output_tokens + resp2.output_tokens,
                    "model": resp2.model,
                    "latency_ms": resp.latency_ms + resp2.latency_ms,
                    "status": "success_after_retry",
                }
                self.cache.set(features, self.prompt_version, self.model_name, result2)
                return result2

            except Exception as final_exc:
                logger.error(
                    "[DiagnosisAgent] Attempt 2 failed: %s. Falling back to unknown.", final_exc
                )
                fallback = DiagnosisResult(
                    device_id=alert.device_id,
                    cause=DiagnosisCause.UNKNOWN,
                    confidence=0.0,
                    evidence=[
                        scan_free_text("schema_failure: response failed validation after retry")
                    ],
                    prompt_version=self.prompt_version,
                    model=self.model_name,
                    prompt_hash=self.prompt_hash,
                )
                self.last_call_metadata = {
                    "attempts": 2,
                    "status": "schema_failure",
                    "error": str(final_exc),
                }
                return fallback

        except (LLMTimeoutError, LLMUnavailableError) as err:
            logger.error("[DiagnosisAgent] LLM unavailable: %s", err)
            self.last_call_metadata = {
                "attempts": 1,
                "status": "llm_unavailable",
                "error": str(err),
            }
            return DiagnosisResult(
                device_id=alert.device_id,
                cause=DiagnosisCause.UNKNOWN,
                confidence=0.0,
                evidence=[
                    scan_free_text("llm_unavailable: model request timed out or unavailable")
                ],
                prompt_version=self.prompt_version,
                model=self.model_name,
                prompt_hash=self.prompt_hash,
            )

    def _parse_and_validate(
        self, text: str, expected_device_id: str, model: str
    ) -> DiagnosisResult:
        """Parse raw JSON, validate schema and constraints, and scan free text."""
        cleaned = _strip_json_fences(text)
        data = json.loads(cleaned)

        raw_evidence = data.get("evidence", [])
        if not isinstance(raw_evidence, list) or not (1 <= len(raw_evidence) <= 3):
            raise ValueError("Evidence must be a list containing between 1 and 3 items")

        scanned_evidence = [scan_free_text(str(e)) for e in raw_evidence]

        return DiagnosisResult(
            device_id=expected_device_id,
            cause=DiagnosisCause(data["cause"]),
            confidence=float(data["confidence"]),
            evidence=scanned_evidence,
            prompt_version=self.prompt_version,
            model=model,
            prompt_hash=self.prompt_hash,
        )
