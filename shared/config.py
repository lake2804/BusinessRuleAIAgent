"""Shared runtime configuration."""
import os
from typing import Dict, List


AVAILABLE_MODELS: Dict[str, List[str]] = {
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "qwen/qwen3-32b",
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
}

DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
}

API_KEY_ENV_VARS = {
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def get_providers() -> List[str]:
    return list(AVAILABLE_MODELS.keys())


def normalize_provider(provider: str | None) -> str:
    providers = get_providers()
    if provider in providers:
        return provider
    return providers[0]


def get_models(provider: str) -> List[str]:
    return AVAILABLE_MODELS.get(provider, [])


def get_default_model(provider: str) -> str:
    models = get_models(provider)
    configured_default = DEFAULT_MODELS.get(provider)
    if configured_default in models:
        return configured_default
    return models[0] if models else ""


def normalize_model(provider: str, model: str | None) -> str:
    models = get_models(provider)
    if model in models:
        return model
    return get_default_model(provider)


def get_api_key(provider: str) -> str:
    env_var = API_KEY_ENV_VARS.get(provider)
    return os.getenv(env_var, "") if env_var else ""


def get_api_key_env_var(provider: str) -> str:
    return API_KEY_ENV_VARS.get(provider, "")
