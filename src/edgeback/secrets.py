import re


# Redacts basic API keys that might mistakenly get logged.
# It is important that real keys are in .env and the run configs are sanitized.
def redact_secrets(text: str) -> str:
    """
    Naive redactor for common secret patterns.
    """
    # Specifically target common key shapes (e.g. APCA-API-KEY-ID, etc)
    # Simple replace for tests:
    replaced = re.sub(r"([A-Z0-9]{20,})", r"***REDACTED***", text)
    return replaced
