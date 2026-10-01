"""One provider factory for council, prompt synthesis and expert lenses."""
import asyncio
import os
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from .prompts import CLAUDE_MODELS,OPENAI_MODELS,DEFAULT_MODEL
from .execution import current_execution
from . import usage

HF_MODELS=['meta-llama/Llama-3.3-70B-Instruct','Qwen/Qwen2.5-72B-Instruct','deepseek-ai/DeepSeek-V3-0324','mistralai/Mistral-Small-24B-Instruct-2501']
HF_BASE_URL='https://router.huggingface.co/v1'
MAX_TOKENS=8000
DEFAULT_AGENT_MODELS={'intake':'claude-haiku-4-5','analyst':'claude-sonnet-5','reviewer':'claude-opus-5','client':'claude-opus-5','custom':'claude-sonnet-5'}
_DISPATCH=asyncio.Semaphore(2)

class ConfigError(Exception):pass

def default_provider():return os.getenv('MRA_DEFAULT_PROVIDER','openai')
def default_model():return os.getenv('MRA_DEFAULT_MODEL','gpt-5-mini')
def server_key_available():return bool(os.getenv('OPENAI_API_KEY') if default_provider()=='openai' else os.getenv('ANTHROPIC_API_KEY'))

def resolve_model(settings,agent_key,agent_model=None):
    settings=settings or {}
    provider=settings.get('provider') or default_provider()
    model=(settings.get('model') or '').strip()
    if provider=='openai':return model if model in OPENAI_MODELS else default_model()
    if provider=='hf':return model or HF_MODELS[0]
    if provider!='claude':raise ConfigError('Unknown provider')
    if agent_model and agent_model in CLAUDE_MODELS:return agent_model
    if model not in ('','auto'):return model if model in CLAUDE_MODELS else DEFAULT_MODEL
    return DEFAULT_AGENT_MODELS.get(agent_key,DEFAULT_MODEL)

class MeteredModel:
    def __init__(self,model,provider,name,max_tokens,shared,structured=False):
        self.model,self.provider,self.name,self.max_tokens,self.shared,self.structured=model,provider,name,max_tokens,shared,structured
    def bind_tools(self,tools):
        return MeteredModel(self.model.bind_tools(tools),self.provider,self.name,self.max_tokens,self.shared)
    def with_structured_output(self,schema,**kwargs):
        kwargs.pop('include_raw',None)
        return MeteredModel(self.model.with_structured_output(schema,include_raw=True,**kwargs),self.provider,self.name,self.max_tokens,self.shared,True)
    async def ainvoke(self,messages):
        async with _DISPATCH:
            reservation=await usage.reserve(self.provider,self.name,messages,self.max_tokens,self.shared)
            try:
                result=await self.model.ainvoke(messages)
                raw=result.get('raw') if self.structured else result
                await usage.settle(reservation,self.provider,self.name,raw)
                if self.structured:
                    if result.get('parsing_error') or result.get('parsed') is None:
                        raise ConfigError('The model returned an invalid structured response')
                    return result['parsed']
                return result
            except BaseException:
                await asyncio.shield(usage.failed(reservation))
                raise

def build_llm(settings,agent_key='analyst',agent_model=None,*,max_tokens=MAX_TOKENS):
    scope=current_execution()
    if scope.mode in {'cached','mock'} or os.getenv('MRA_MOCK_MODE')=='1':
        from .examples import FixtureModel
        return FixtureModel(agent_key)
    settings=settings or {}
    provider=settings.get('provider') or default_provider()
    user_key=(settings.get('api_key') or '').strip()
    model=resolve_model(settings,agent_key,agent_model)
    if not 1<=max_tokens<=MAX_TOKENS:raise ConfigError('Invalid output limit')
    if provider=='openai':
        key=user_key or (os.getenv('OPENAI_API_KEY','') if default_provider()=='openai' else '')
        if not key:raise ConfigError('Add an OpenAI key in Settings or use a prepared example')
        raw=ChatOpenAI(model=model,api_key=key,max_completion_tokens=max_tokens,reasoning_effort='low',timeout=90,max_retries=0)
    elif provider=='hf':
        if not user_key:raise ConfigError('Add your Hugging Face token in Settings')
        raw=ChatOpenAI(model=model,api_key=user_key,base_url=HF_BASE_URL,max_completion_tokens=max_tokens,timeout=90,max_retries=0)
    else:
        key=user_key or (os.getenv('ANTHROPIC_API_KEY','') if default_provider()=='claude' else '')
        if not key:raise ConfigError('Add an Anthropic key in Settings or use a prepared example')
        raw=ChatAnthropic(model=model,api_key=key,max_tokens=max_tokens,timeout=90,max_retries=0)
    return MeteredModel(raw,provider,model,max_tokens,not bool(user_key))
