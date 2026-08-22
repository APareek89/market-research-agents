"""Model factory: builds a LangChain chat model from the per-request settings.
Default = server's Anthropic key (env). Users may bring their own Claude or
OpenAI key (Tab 4); user keys are request-scoped and never persisted."""

import os

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from .prompts import CLAUDE_MODELS, OPENAI_MODELS, DEFAULT_MODEL

MAX_TOKENS = 8000


class ConfigError(Exception):
    pass


def build_llm(settings: dict):
    """settings: {provider: 'claude'|'openai', model: str, api_key: str|''}"""
    provider = (settings or {}).get("provider") or "claude"
    model = (settings or {}).get("model") or DEFAULT_MODEL
    user_key = ((settings or {}).get("api_key") or "").strip()

    if provider == "openai":
        if not user_key:
            raise ConfigError("OpenAI models need your own API key — add it in the Settings tab.")
        if model not in OPENAI_MODELS:
            model = OPENAI_MODELS[0]
        return ChatOpenAI(model=model, api_key=user_key, max_completion_tokens=MAX_TOKENS, timeout=180)

    key = user_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ConfigError("No Anthropic API key configured on the server — add your own key in Settings.")
    if model not in CLAUDE_MODELS:
        model = DEFAULT_MODEL
    # Claude opus-5/sonnet-5 reject sampling params; pass only model/key/limits.
    return ChatAnthropic(model=model, api_key=key, max_tokens=MAX_TOKENS, timeout=180)
