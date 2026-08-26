from observability.logging import redact


def test_redacts_common_secret_fields():
    value = 'api_key="super-secret" authorization=Bearer-token password=hunter2'
    redacted = redact(value)
    assert "super-secret" not in redacted
    assert "Bearer-token" not in redacted
    assert "hunter2" not in redacted
