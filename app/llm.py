"""Model factory: builds a LangChain chat model from the per-request settings.
Default = server's Anthropic key (env). Users may bring their own Claude or
OpenAI key (Tab 4); user keys are request-scoped and never persisted."""

import os

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from .prompts import CLAUDE_MODELS, OPENAI_MODELS, DEFAULT_MODEL

# Preset suggestions for the Hugging Face router; any HF model id is accepted.
HF_MODELS = [
    "meta-llama/Llama-3.3-70B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct",
    "deepseek-ai/DeepSeek-V3-0324",
    "mistralai/Mistral-Small-24B-Instruct-2501",
]
HF_BASE_URL = "https://router.huggingface.co/v1"

MAX_TOKENS = 8000

# "Auto" mix: fast model for intake, balanced for the analyst and custom agents,
# strongest for the reviewers.
DEFAULT_AGENT_MODELS = {
    "intake": "claude-haiku-4-5",
    "analyst": "claude-sonnet-5",
    "reviewer": "claude-opus-5",
    "client": "claude-opus-5",
    "custom": "claude-sonnet-5",
}


class ConfigError(Exception):
    pass


def resolve_model(settings: dict, agent_key: str, agent_model: str | None = None) -> str:
    """Precedence: per-agent model > global pinned model > per-role auto default.
    OpenAI provider always uses the single global GPT model."""
    provider = (settings or {}).get("provider") or "claude"
    global_model = ((settings or {}).get("model") or "").strip()
    if provider == "openai":
        return global_model if global_model in OPENAI_MODELS else OPENAI_MODELS[0]
    if provider == "hf":
        return global_model or HF_MODELS[0]
    per_agent = (agent_model or "").strip()
    if per_agent and per_agent != "auto" and per_agent in CLAUDE_MODELS:
        return per_agent
    if global_model not in ("", "auto"):
        return global_model if global_model in CLAUDE_MODELS else DEFAULT_MODEL
    return DEFAULT_AGENT_MODELS.get(agent_key, DEFAULT_MODEL)


def build_llm(settings: dict, agent_key: str = "analyst", agent_model: str | None = None):
    """settings: {provider: 'claude'|'openai', model: str|'auto', api_key: str|''}"""
    provider = (settings or {}).get("provider") or "claude"
    user_key = ((settings or {}).get("api_key") or "").strip()
    model = resolve_model(settings, agent_key, agent_model)

    if provider == "openai":
        if not user_key:
            raise ConfigError("OpenAI models need your own API key — add it in the Settings tab.")
        return ChatOpenAI(model=model, api_key=user_key, max_completion_tokens=MAX_TOKENS, timeout=180)

    if provider == "hf":
        if not user_key:
            raise ConfigError("Hugging Face models need your HF token — add it in the Settings tab.")
        # HF Inference Providers router speaks the OpenAI protocol.
        return ChatOpenAI(model=model, api_key=user_key, base_url=HF_BASE_URL,
                          max_completion_tokens=MAX_TOKENS, timeout=180)

    key = user_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise ConfigError("No Anthropic API key configured on the server — add your own key in Settings.")
    # Claude opus-5/sonnet-5 reject sampling params; pass only model/key/limits.
    return ChatAnthropic(model=model, api_key=key, max_tokens=MAX_TOKENS, timeout=180)
