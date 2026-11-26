"""Read and update provider preferences using the installed Hermes runtime."""
import json
import re
from contextlib import redirect_stdout
from io import StringIO
import sys
from urllib.parse import urlsplit


class ProviderInputError(ValueError):
    pass


def provider_options(config):
    from hermes_cli.auth import PROVIDER_REGISTRY
    from hermes_cli.config import get_compatible_custom_providers
    from hermes_cli.models import CANONICAL_PROVIDERS
    from hermes_cli.providers import custom_provider_slug

    options = {row.slug: {"id": row.slug, "name": row.tui_desc or row.slug, "key_env": "", "interactive": True}
               for row in CANONICAL_PROVIDERS}
    for provider_id, profile in PROVIDER_REGISTRY.items():
        key_env = profile.api_key_env_vars[0] if profile.auth_type == "api_key" and profile.api_key_env_vars else ""
        options[provider_id] = {"id": provider_id, "name": profile.name, "key_env": key_env,
                                "interactive": not key_env or provider_id == "azure-foundry"}
    options["openrouter"] = {"id": "openrouter", "name": "OpenRouter", "key_env": "OPENROUTER_API_KEY", "interactive": False}
    for entry in get_compatible_custom_providers(config):
        provider_id = custom_provider_slug(entry["name"], entry.get("provider_key"))
        options[provider_id] = {"id": provider_id, "name": entry["name"], "key_env": "", "interactive": False}
    return sorted(options.values(), key=lambda option: option["name"].casefold())


def update_model(config, request, options):
    provider_id = request["provider"]
    model = request["model"].strip()
    key = request.get("api_key", "")
    if not model or len(model) > 256 or not model.isprintable():
        raise ProviderInputError("Enter a valid model ID.")
    if len(key) > 4096 or any(character.isspace() or not character.isprintable() for character in key):
        raise ProviderInputError("Enter an API key as a single value without spaces.")

    if provider_id == "new-custom":
        name = request.get("name", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,39})", name):
            raise ProviderInputError("Use a short endpoint name with letters, digits, and hyphens.")
        url = request.get("base_url", "").strip().rstrip("/")
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise ProviderInputError("Enter a valid OpenAI-compatible base URL.") from None
        if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None
                or parts.query or parts.fragment or port == 0 or len(url) > 1024
                or any(character.isspace() or not character.isprintable() for character in url)):
            raise ProviderInputError("Use an HTTP(S) base URL without credentials, a query, or a fragment.")
        slug = "coral-" + name.lower()
        provider_id = "custom:" + slug
        providers = config.setdefault("providers", {})
        existing = providers.get(slug, {})
        key_env = "CORAL_PROVIDER_" + name.upper().replace("-", "_") + "_API_KEY"
        entry = {"name": name, "api": url, "transport": "chat_completions", "default_model": model}
        if key or (existing.get("api") == url and existing.get("key_env") == key_env):
            entry["key_env"] = key_env
        providers[slug] = entry
    else:
        option = next((option for option in options if option["id"] == provider_id), None)
        if option is None:
            raise ProviderInputError("Choose a provider available in this Hermes installation.")
        key_env = option["key_env"]
        if key and (not key_env or option["interactive"]):
            raise ProviderInputError("Use Hermes’ interactive setup to authenticate this provider.")

    existing = config.get("model")
    existing = dict(existing) if isinstance(existing, dict) else {}
    if request["provider"] == "new-custom" or existing.get("provider") != provider_id:
        for setting in ("base_url", "api_key", "key_env", "api_key_env", "key_cmd", "api_mode", "context_length"):
            existing.pop(setting, None)
    config["model"] = {**existing, "provider": provider_id, "default": model}
    return key_env, key


def run(request):
    from hermes_cli.config import (is_managed, load_config, load_env, remove_env_value,
                                   require_readable_config_before_write, save_config, save_env_value)

    if request["operation"] == "provider_options":
        config = load_config()
        model = config.get("model")
        if not isinstance(model, dict):
            model = {"default": model}
        return {"providers": provider_options(config), "selected": str(model.get("provider") or ""),
                "model": str(model.get("default") or "")}

    if is_managed():
        raise ProviderInputError("Hermes configuration is managed in this Codespace.")
    config = require_readable_config_before_write()
    key_env, key = update_model(config, request, provider_options(load_config()))
    previous = load_env().get(key_env) if key else None
    if key:
        save_env_value(key_env, key)
    try:
        save_config(config)
    except Exception:
        if key:
            if previous is None:
                remove_env_value(key_env)
            else:
                save_env_value(key_env, previous)
        raise
    return {"saved": True}


if __name__ == "__main__":
    try:
        with redirect_stdout(StringIO()):
            result = run(json.load(sys.stdin))
    except ProviderInputError as error:
        result = {"error": str(error)}
    except Exception:
        result = {"error": "Hermes could not read or save the provider. Check its configuration over SSH."}
    print(json.dumps(result))
