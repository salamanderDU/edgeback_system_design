from edgeback.secrets import redact_secrets


def test_secrets_redaction() -> None:
    """Ensure basic potential keys are redacted."""
    sensitive_log = "Error connecting to provider with api key AKIAIOSFODNN7EXAMPLE"
    redacted = redact_secrets(sensitive_log)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "***REDACTED***" in redacted


def test_no_secrets_are_untouched() -> None:
    safe_log = "Error parsing config file: example_backtest.yaml"
    assert redact_secrets(safe_log) == safe_log
