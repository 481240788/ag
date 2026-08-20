from config import Settings


def test_settings_can_be_injected_without_env():
    settings = Settings(
        model_name="test-model",
        llm_base_url="https://example.invalid/v1",
        llm_api_key="secret",
    )
    assert settings.max_agent_iterations == 10
    assert settings.search_api_key is None


def test_settings_accepts_legacy_env_names(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "model_name=test\nbase_url=https://example.invalid\napi=key\n",
        encoding="utf-8",
    )
    settings = Settings.from_env(env_file)
    assert settings.model_name == "test"
    assert settings.llm_api_key == "key"
