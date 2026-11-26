import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location("workspace_providers", Path(__file__).resolve().parents[2] / "codespace/providers.py")
providers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(providers)


def test_provider_options_include_registered_and_saved_providers(monkeypatch):
    catalog = [SimpleNamespace(slug="catalog-only", tui_desc="Catalog OAuth")]
    registry = {"plugin": SimpleNamespace(name="Installed Plugin", auth_type="api_key", api_key_env_vars=("PLUGIN_KEY",))}
    for module, globals_ in {
        "auth": {"PROVIDER_REGISTRY": registry},
        "config": {"get_compatible_custom_providers": lambda _: [{"name": "Local", "provider_key": "local"}]},
        "models": {"CANONICAL_PROVIDERS": catalog},
        "providers": {"custom_provider_slug": lambda _, key: "custom:" + key},
    }.items():
        monkeypatch.setitem(sys.modules, f"hermes_cli.{module}", SimpleNamespace(**globals_))

    options = {option["id"]: option for option in providers.provider_options({})}
    assert options["catalog-only"]["interactive"]
    assert options["plugin"]["key_env"] == "PLUGIN_KEY"
    assert options["openrouter"]["key_env"] == "OPENROUTER_API_KEY"
    assert options["custom:local"]["name"] == "Local"


def test_custom_endpoint_keeps_the_key_separate_from_the_route():
    config = {"model": {"provider": "openai-api", "base_url": "https://previous.example/v1", "api_key": "previous"}}
    request = {"provider": "new-custom", "model": "qwen/test", "name": "lab", "base_url": "https://example.org/v1/", "api_key": "test-key"}
    variable, key = providers.update_model(config, request, [])
    assert (variable, key) == ("CORAL_PROVIDER_LAB_API_KEY", "test-key")
    assert config["model"] == {"provider": "custom:coral-lab", "default": "qwen/test"}
    assert config["providers"]["coral-lab"] == {"name": "lab", "api": "https://example.org/v1",
                                                 "transport": "chat_completions", "default_model": "qwen/test", "key_env": variable}
    assert "test-key" not in str(config)

    providers.update_model(config, {**request, "base_url": "http://localhost:4000/v1", "api_key": ""}, [])
    assert "key_env" not in config["providers"]["coral-lab"]


def test_provider_setup_rejects_urls_with_inline_credentials():
    with pytest.raises(providers.ProviderInputError, match="without credentials"):
        providers.update_model({}, {"provider": "new-custom", "model": "local", "name": "lab",
                                    "base_url": "https://user:password@example.org/v1"}, [])
