"""Configuration loading and validation module.

Purpose: Loads non-secret settings from YAML and secret values from environment variables.
Inputs: Path to YAML settings file, OS environment variables.
Outputs: Typed, validated Settings instance.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from iir.common.errors import ConfigError


class LimitsConfig(BaseModel):
    """API rate limits and payload size constraints."""

    requests_per_minute_per_key: int = 60
    requests_per_day_per_key: int = 2000
    llm_calls_per_day_per_key: int = 200
    concurrent_jobs_per_key: int = 2
    max_request_body_bytes: int = 16384
    max_free_text_chars: int = 4000
    list_limit_clamp: int = 200


class TokensConfig(BaseModel):
    """LLM token budgets and per-call token caps."""

    per_run_budget: int = 200000
    per_day_global_budget: int = 1000000
    diagnosis_output_cap: int = 300
    diagnosis_input_cap: int = 1500
    remediation_output_cap: int = 200
    remediation_input_cap: int = 800


class LoadConfig(BaseModel):
    """Load control, cooldown, retry, and circuit breaker settings."""

    max_concurrent_llm_calls: int = 4
    alert_queue_max_size: int = 50
    alert_cooldown_seconds: int = 300
    provider_max_retries: int = 3
    circuit_breaker_consecutive_failures: int = 5
    circuit_breaker_failure_window_seconds: int = 60
    circuit_breaker_open_duration_seconds: int = 60
    llm_timeout_seconds: int = 20
    db_timeout_seconds: int = 10
    diagnosis_cache_ttl_hours: int = 24


class MqttSettings(BaseModel):
    """MQTT communication options."""

    host: str = "localhost"
    port: int = 1883
    tls: bool = False
    qos: int = 1
    max_payload_bytes: int = 2048


REQUIRED_SECRETS: tuple[str, ...] = (
    "MQTT_PASSWORD",
    "API_KEY_PEPPER",
    "LLM_API_KEY",
)


class Settings(BaseSettings):
    """Application settings combining YAML non-secrets and environment secrets."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_ignore_empty=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    mqtt_host: str = Field(default="localhost", validation_alias="MQTT_HOST")
    mqtt_port: int = Field(default=1883, validation_alias="MQTT_PORT")
    mqtt_username: str = Field(default="simulator", validation_alias="MQTT_USERNAME")
    mqtt_password: str = Field(default="", validation_alias="MQTT_PASSWORD")
    mqtt_tls: bool = Field(default=False, validation_alias="MQTT_TLS")
    api_key_pepper: str = Field(default="", validation_alias="API_KEY_PEPPER")
    llm_provider: str = Field(default="mock", validation_alias="LLM_PROVIDER")
    llm_model: str = Field(default="mock-model", validation_alias="LLM_MODEL")
    llm_api_key: str = Field(default="", validation_alias="LLM_API_KEY")

    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    tokens: TokensConfig = Field(default_factory=TokensConfig)
    load: LoadConfig = Field(default_factory=LoadConfig)
    mqtt: MqttSettings = Field(default_factory=MqttSettings)


def load_yaml_config(path: Path | str) -> dict[str, Any]:
    """Load non-secret YAML settings file safely."""
    target = Path(path)
    if not target.is_file():
        raise ConfigError(f"Settings file not found: {target}")
    with target.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return {}
    return data


def load_settings(
    yaml_path: Path | str = "config/settings.yaml",
    env_override: dict[str, str] | None = None,
    enforce_secrets: bool = True,
) -> Settings:
    """Load and validate system settings.

    Args:
        yaml_path: Path to the non-secret settings YAML.
        env_override: Optional dictionary of environment overrides.
        enforce_secrets: When True, checks that required secrets exist in environment.

    Raises:
        ConfigError: When a required secret is missing or validation fails.
    """
    env_source = os.environ if env_override is None else env_override

    if enforce_secrets:
        for secret_name in REQUIRED_SECRETS:
            val = env_source.get(secret_name)
            if not val or not val.strip():
                raise ConfigError(
                    variable_name=secret_name,
                    message=f"Missing required configuration secret: {secret_name}",
                )

    yaml_data = load_yaml_config(yaml_path)

    # Inject environment variables
    combined_data: dict[str, Any] = dict(yaml_data)
    for key, val in env_source.items():
        combined_data[key] = val

    try:
        return Settings(**combined_data)
    except Exception as exc:
        raise ConfigError(
            variable_name="SETTINGS_VALIDATION",
            message=f"Settings validation failed: {exc}",
        ) from exc
