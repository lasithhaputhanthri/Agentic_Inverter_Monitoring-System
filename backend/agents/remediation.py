"""Remediation agent for recommending conservative corrective actions.

Purpose: Formulates safe action proposals based on diagnosed failure causes, enforcing
         strict device verification, token limits, single-retry resilience, and output sanitization.
Inputs: Alert instance and DiagnosisResult.
Outputs: Validated, immutable ActionProposal.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from pydantic import ValidationError

from backend.agents.cache import AgentCache
from backend.agents.guard import scan_free_text
from backend.agents.llm_client import LLMClient
from backend.agents.models import ActionProposal, DiagnosisResult, RemediationAction
from backend.agents.prompts import load_prompt
from backend.agents.quota import QuotaTracker, estimate_tokens
from backend.common.errors import LLMQuotaExceededError, LLMTimeoutError, LLMUnavailableError
from backend.common.logging import get_logger
from backend.monitor.models import Alert

logger = get_logger(__name__)

REMEDIATION_INPUT_TOKEN_CAP: int = 800
REMEDIATION_OUTPUT_TOKEN_CAP: int = 200


def _escape_data(val: str) -> str:
    """Escape angle brackets so data cannot close XML delimiter blocks."""
    return val.replace("<", "&lt;").replace(">", "&gt;")


def _strip_json_fences(text: str) -> str:
    """Extract raw JSON from markdown fences if present."""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start : end + 1].strip()
    return cleaned


class RemediationAgent:
    """Agent that recommends safe remediation actions based on diagnosed incidents."""

    def __init__(
        self,
        client: LLMClient,
        cache: AgentCache | None = None,
        quota: QuotaTracker | None = None,
        prompt_version: str = "remediation_v1",
        model_name: str = "mock-model",
    ) -> None:
        self.client = client
        self.cache = cache or AgentCache()
        self.quota = quota or QuotaTracker()
        self.prompt_version = prompt_version
        self.model_name = model_name
        self.prompt_text, self.prompt_hash = load_prompt(f"{prompt_version}.txt")
        self.last_call_metadata: dict[str, Any] = {}

    def _build_prompt(self, alert: Alert, diagnosis: DiagnosisResult) -> str:
        """Assemble delimited prompt within the 800 input token budget."""
        alert_json = json.dumps(
            {
                "alert_id": str(alert.alert_id),
                "device_id": alert.device_id,
                "rule": alert.rule.value,
                "severity": alert.severity.value,
                "observed": alert.observed,
                "threshold": alert.threshold,
            },
            sort_keys=True,
        )
        diag_json = json.dumps(
            {
                "device_id": diagnosis.device_id,
                "cause": diagnosis.cause.value,
                "confidence": diagnosis.confidence,
                "evidence": diagnosis.evidence,
            },
            sort_keys=True,
        )

        escaped_alert = _escape_data(alert_json)
        escaped_diag = _escape_data(diag_json)

        full_prompt = (
            f"{self.prompt_text}\n\n"
            f"<alert>\n{escaped_alert}\n</alert>\n\n"
            f"<diagnosis>\n{escaped_diag}\n</diagnosis>\n"
        ).strip()

        if estimate_tokens(full_prompt) > REMEDIATION_INPUT_TOKEN_CAP:
            raise LLMQuotaExceededError(
                f"Remediation prompt exceeds input token ceiling ({REMEDIATION_INPUT_TOKEN_CAP})"
            )

        return full_prompt

    def propose_action(
        self,
        alert: Alert,
        diagnosis: DiagnosisResult,
    ) -> ActionProposal:
        """Recommend a remediation action with device validation, quota checks, and fallback."""
        # SEC-33 check: Diagnosis device must match alert device
        if diagnosis.device_id != alert.device_id:
            raise ValueError(
                f"Device mismatch: diagnosis device ({diagnosis.device_id}) differs from alert ({alert.device_id})"
            )

        features = {
            "alert": alert.model_dump(mode="json"),
            "diagnosis": diagnosis.model_dump(mode="json"),
        }
        cached = self.cache.get(features, self.prompt_version, self.model_name)
        if cached is not None and isinstance(cached, ActionProposal):
            return cast(ActionProposal, cached)

        prompt = self._build_prompt(alert, diagnosis)

        # Attempt 1
        self.quota.check_call_quota()
        self.quota.record_call()

        try:
            resp = self.client.generate(
                prompt=prompt,
                max_tokens=REMEDIATION_OUTPUT_TOKEN_CAP,
                temperature=0.0,
            )
            proposal = self._parse_and_validate(
                resp.text, alert.device_id, str(diagnosis.cause), resp.model
            )
            self.last_call_metadata = {
                "attempts": 1,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "model": resp.model,
                "latency_ms": resp.latency_ms,
                "status": "success",
            }
            self.cache.set(features, self.prompt_version, self.model_name, proposal)
            return proposal

        except (json.JSONDecodeError, ValidationError, ValueError, KeyError) as exc:
            logger.warning(
                "[RemediationAgent] Attempt 1 validation error: %s. Retrying once...", exc
            )

            # Retry once
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
                    max_tokens=REMEDIATION_OUTPUT_TOKEN_CAP,
                    temperature=0.0,
                )
                proposal2 = self._parse_and_validate(
                    resp2.text, alert.device_id, str(diagnosis.cause), resp2.model
                )
                self.last_call_metadata = {
                    "attempts": 2,
                    "input_tokens": resp.input_tokens + resp2.input_tokens,
                    "output_tokens": resp.output_tokens + resp2.output_tokens,
                    "model": resp2.model,
                    "latency_ms": resp.latency_ms + resp2.latency_ms,
                    "status": "success_after_retry",
                }
                self.cache.set(features, self.prompt_version, self.model_name, proposal2)
                return proposal2

            except Exception as final_exc:
                logger.error(
                    "[RemediationAgent] Attempt 2 failed: %s. Falling back to no_action.", final_exc
                )
                fallback = ActionProposal(
                    device_id=alert.device_id,
                    action=RemediationAction.NO_ACTION,
                    justification=scan_free_text(
                        "schema_failure: response failed validation after retry"
                    ),
                    diagnosis_ref=str(diagnosis.cause),
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
            logger.error("[RemediationAgent] LLM unavailable: %s", err)
            self.last_call_metadata = {
                "attempts": 1,
                "status": "llm_unavailable",
                "error": str(err),
            }
            return ActionProposal(
                device_id=alert.device_id,
                action=RemediationAction.NO_ACTION,
                justification=scan_free_text(
                    "llm_unavailable: model request timed out or unavailable"
                ),
                diagnosis_ref=str(diagnosis.cause),
                prompt_version=self.prompt_version,
                model=self.model_name,
                prompt_hash=self.prompt_hash,
            )

    def _parse_and_validate(
        self,
        text: str,
        expected_device_id: str,
        diagnosis_ref: str,
        model: str,
    ) -> ActionProposal:
        """Parse raw JSON, enforce device matching (SEC-33), and sanitize justification text."""
        cleaned = _strip_json_fences(text)
        data = json.loads(cleaned)

        raw_justification = str(data.get("justification", ""))
        scanned_justification = scan_free_text(raw_justification)

        # Allow model output to specify device_id, but SEC-33 requires it must match expected_device_id
        emitted_device = data.get("device_id", expected_device_id)
        if emitted_device != expected_device_id:
            raise ValueError(
                f"SEC-33 Violation: Proposal target device '{emitted_device}' does not match alert device '{expected_device_id}'"
            )

        return ActionProposal(
            device_id=expected_device_id,
            action=RemediationAction(data["action"]),
            justification=scanned_justification,
            diagnosis_ref=diagnosis_ref,
            prompt_version=self.prompt_version,
            model=model,
            prompt_hash=self.prompt_hash,
        )
