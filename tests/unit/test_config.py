"""Unit tests for configuration loading and secret handling.

Purpose: Verifies environment secret enforcement and YAML non-secret loading.
Inputs: Synthetic environment dictionaries and YAML settings.
Outputs: Assertion checks on ConfigError and Settings contents.
"""

from __future__ import annotations

import pytest
from backend.common.config import REQUIRED_SECRETS, load_settings
from backend.common.errors import ConfigError


def test_missing_secret_raises_config_error_without_value() -> None:
    """A config load with a missing secret raises ConfigError naming variable without printing value."""
    # Test each required secret individually
    for missing_secret in REQUIRED_SECRETS:
        mock_env = {
            "MQTT_PASSWORD": "secret_mqtt_pw",
            "API_KEY_PEPPER": "secret_pepper_min_32_characters_123",
            "LLM_API_KEY": "secret_llm_key_mock_value",
        }
        # Remove one required secret
        del mock_env[missing_secret]

        with pytest.raises(ConfigError) as exc_info:
            load_settings(
                yaml_path="config/settings.yaml", env_override=mock_env, enforce_secrets=True
            )

        err_msg = str(exc_info.value)
        # Must name the variable
        assert missing_secret in err_msg
        assert exc_info.value.variable_name == missing_secret

        # Must never print any other secret value in the error message
        for _other_secret_name, other_secret_val in mock_env.items():
            assert other_secret_val not in err_msg


def test_successful_config_load_from_yaml_and_env() -> None:
    """Config loads defaults from YAML and overrides/secrets from env."""
    mock_env = {
        "MQTT_PASSWORD": "test_mqtt_password",
        "API_KEY_PEPPER": "test_pepper_long_secret_phrase_123",
        "LLM_API_KEY": "test_llm_key",
        "APP_ENV": "test",
    }
    settings = load_settings(yaml_path="config/settings.yaml", env_override=mock_env)

    # Secrets
    assert settings.mqtt_password == "test_mqtt_password"
    assert settings.api_key_pepper == "test_pepper_long_secret_phrase_123"
    assert settings.llm_api_key == "test_llm_key"
    assert settings.app_env == "test"

    # YAML non-secrets
    assert settings.limits.requests_per_minute_per_key == 60
    assert settings.limits.max_request_body_bytes == 16384
    assert settings.tokens.diagnosis_output_cap == 300
    assert settings.load.alert_queue_max_size == 50
    assert settings.mqtt.qos == 1
