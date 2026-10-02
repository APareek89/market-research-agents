"""Offline failure-boundary regressions; fake responses are not provider acceptance."""
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from app.llm import MeteredModel, ConfigError, validate_completion
from app.main import validate_config
from app.execution import Execution,execution_scope

class InputContracts(unittest.TestCase):
    def test_review_switches_never_coerce_truthy_strings_into_paid_stages(self):
        for field in ('enable_reviewer','enable_client'):
            for bad in ('false',1,[],{}):
                with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):validate_config(json.dumps({field:bad}))
        self.assertEqual(validate_config('{"enable_reviewer":false}')['enable_reviewer'],False)
    def test_custom_and_expert_switches_and_modes_are_strict(self):
        for cfg in ({'agents':{'reviewer':{'expert_mode':'false'}}},{'custom_agents':[{'id':'x','enabled':'false'}]},{'custom_agents':[{'id':'x','mode':'typo'}]}):
            with self.subTest(cfg=cfg),self.assertRaises(ValueError):validate_config(json.dumps(cfg))
    def test_completion_markers_and_tool_calls_are_required(self):
        for provider,field,valid in [('openai','finish_reason','stop'),('hf','finish_reason','stop'),('claude','stop_reason','end_turn')]:
            validate_completion(SimpleNamespace(response_metadata={field:valid},content='Complete answer.'),provider)
            for bad in (None,'length','max_tokens','content_filter','refusal','unknown'):
                with self.subTest(provider=provider,bad=bad),self.assertRaises(ConfigError):
                    validate_completion(SimpleNamespace(response_metadata={field:bad}),provider)
        with self.assertRaises(ConfigError):validate_completion(SimpleNamespace(response_metadata={'finish_reason':'tool_calls'},tool_calls=[]),'openai')
        validate_completion(AIMessage(content='',tool_calls=[{'id':'call-1','name':'fetch_url','args':{'url':'https://example.com'}}],response_metadata={'finish_reason':'tool_calls'}),'openai')
        for content in ['', ' \n ', [], [{'type':'text','text':' '}]]:
            with self.subTest(content=content),self.assertRaises(ConfigError):validate_completion(SimpleNamespace(response_metadata={'finish_reason':'stop'},content=content),'openai')

class PaidBoundaryWithoutPayment(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_text_settles_usage_then_fails_without_second_dispatch(self):
        raw=AIMessage(content='partial answer',response_metadata={'finish_reason':'length'},usage_metadata={'input_tokens':10,'output_tokens':4,'total_tokens':14})
        underlying=SimpleNamespace(ainvoke=AsyncMock(return_value=raw))
        with execution_scope(Execution(str(uuid.uuid4()),str(uuid.uuid4()))),patch('app.llm.usage.reserve',AsyncMock(return_value='fixture')),patch('app.llm.usage.settle',AsyncMock()) as settle,patch('app.llm.usage.failed',AsyncMock()),patch('app.llm.logging') as log:
            with self.assertRaises(ConfigError):await MeteredModel(underlying,'openai','gpt-5-mini',20,True).ainvoke([HumanMessage(content='synthetic')])
            logged=json.loads(log.getLogger.return_value.warning.call_args.args[0])
            self.assertEqual(set(logged),{'event','provider','model','request_id','upstream_status','category'})
            self.assertNotIn('partial answer',str(logged));self.assertNotIn('synthetic',str(logged))
        underlying.ainvoke.assert_awaited_once();settle.assert_awaited_once_with('fixture','openai','gpt-5-mini',raw)
