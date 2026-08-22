"""Model factory: builds a LangChain chat model from the per-request settings.
Default = server's Anthropic key (env). Users may bring their own Claude or
OpenAI key (Tab 4); user keys are request-scoped and never persisted."""

import os

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from .prompts import CLAUDE_MODELS, OPENAI_MODELS, DEFAULT_MODEL

MAX_TOKENS = 8000

# "Auto" mix: fast model for intake, balanced for the analyst, strongest for the reviewers.
DEFAULT_AGENT_MODELS = {
    "intake": "claude-haiku-4-5",
    "analyst": "claude-sonnet-5",
    "reviewer": "claude-opus-5",
    "client": "claude-opus-5",
}


class ConfigError(Exception):
    pass


def resolve_model(settings: dict, agent_key: str) -> str:
    provider = (settings or {}).get("provider") or "claude"
    model = ((settings or {}).get("model") or "").strip()
    if provider == "openai":
        return model if model in OPENAI_MODELS else OPENAI_MODELS[0]
    if model in ("", "auto"):
        return DEFAULT_AGENT_MODELS.get(agent_key, DEFAULT_MODEL)
    return model if model in CLAUDE_MODELS else DEFAULT_MODEL


def build_llm(settings: dict, agent_key: str = "analyst"):
    """settings: {provider: 'claude'|'openai', model: str|'auto', api_key: str|''}"""
    provider = (settings or {}).get("provider") or "claude"
    user_key = ((settings or {}).get("api_key") or "").strip()
    model = resolve_model(settings, agent_key)

    if provider == "openai":
        if not user_key:
            raise ConfigError("OpenAI models need your own API key — add it in the Settings tab.")
        return ChatOpenAI(model=model, api_key=user_key, max_completion_tokens=MAX_TOKENS, timeout=180)

    key = user_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ConfigError("No Anthropic API key configured on the server — add your own key in Settings.")
    # Claude opus-5/sonnet-5 reject sampling params; pass only model/key/limits.
    return ChatAnthropic(model=model, api_key=key, max_tokens=MAX_TOKENS, timeout=180)
