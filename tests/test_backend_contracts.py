"""Real graph/database boundaries and actual SDK wire using an offline transport."""
import asyncio
import io
import json
import os
from pathlib import Path
import uuid
import unittest
from unittest.mock import patch
import zipfile

import httpx
from langchain_core.messages import AIMessage,HumanMessage
from langchain_openai import ChatOpenAI as RealOpenAI
from app import db,examples,graph,llm,runs,usage,lenses
from app.execution import Execution,execution_scope,current_execution
from app.extract import extract_file,ExtractError
from app.export import _pdf_via_typst,validate_export

class PersistenceAndProviders(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ.update({'DATABASE_URL':'postgresql://macbook@127.0.0.1:55443/market_auth_test','DATABASE_SSL':'disable','PORTFOLIO_AUTH_ENABLED':'1','NODE_ENV':'development','MRA_MOCK_MODE':'0','MRA_DEFAULT_PROVIDER':'openai','MRA_DEFAULT_MODEL':'gpt-5-mini'})
        await db.init_db()
        self.owner=str(uuid.uuid4());self.other=str(uuid.uuid4())
        for user in [self.owner,self.other]:
            await db.pool().execute('INSERT INTO mra_users(id,email,password_hash) VALUES($1,$2,$3)',db.uid(user),user+'@example.invalid','not-a-login-hash')
        self.scope=Execution(self.owner,str(uuid.uuid4()),'live')
        self.wires=[]
    async def asyncTearDown(self):
        await db.close_db()
    def sdk(self,status=200,content='Offline wire response',structured=False):
        async def handle(request):
            self.wires.append(json.loads(request.content))
            if status!=200:return httpx.Response(status,json={'error':{'message':'synthetic failure','type':'rate_limit_error','code':'insufficient_quota'}})
            value=content(self.wires[-1]) if callable(content) else content
            return httpx.Response(200,json={'id':'offline-test','object':'chat.completion','created':1,'model':'gpt-5-mini','choices':[{'index':0,'message':{'role':'assistant','content':value},'finish_reason':'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130,'prompt_tokens_details':{'cached_tokens':20},'completion_tokens_details':{'reasoning_tokens':5}}})
        def factory(**kwargs):return RealOpenAI(**kwargs,http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        return patch.object(llm,'ChatOpenAI',factory)
    async def test_actual_sdk_wire_single_call_usage_and_owner(self):
        with self.sdk(),execution_scope(self.scope):
            output=await llm.build_llm({'provider':'openai','api_key':'synthetic-wire-only'},'analyst',max_tokens=2048).ainvoke([HumanMessage(content='A synthetic test')])
        self.assertIn('Offline',output.content);self.assertEqual(len(self.wires),1)
        self.assertEqual(self.wires[0]['max_completion_tokens'],2048);self.assertEqual(self.wires[0]['reasoning_effort'],'low')
        row=await db.pool().fetchrow('SELECT * FROM mra_usage WHERE run_id=$1',db.uid(self.scope.run_id))
        self.assertEqual(row['status'],'complete');self.assertEqual(row['cached_input_tokens'],20);self.assertEqual(row['reasoning_output_tokens'],5)
        self.assertEqual(float(row['actual_usd']),.0000805)
        before=row['actual_usd']
        with execution_scope(Execution(self.other,self.scope.run_id,'live')):
            await usage.failed(str(row['id']))
            await usage.settle(str(row['id']),'openai','gpt-5-mini',AIMessage(content='foreign',usage_metadata={'input_tokens':1,'output_tokens':1,'total_tokens':2}))
        self.assertEqual(await db.pool().fetchval('SELECT actual_usd FROM mra_usage WHERE id=$1',row['id']),before)
    async def test_no_sdk_retries_and_unknown_spend_kept(self):
        with self.sdk(429),execution_scope(self.scope):
            with self.assertRaises(Exception):await llm.build_llm({'provider':'openai','api_key':'synthetic-wire-only'}).ainvoke([HumanMessage(content='test')])
        self.assertEqual(len(self.wires),1)
        self.assertEqual(await db.pool().fetchval('SELECT status FROM mra_usage WHERE run_id=$1',db.uid(self.scope.run_id)),'uncertain')
    async def test_structured_parse_failure_preserves_known_usage(self):
        with self.sdk(content='not valid JSON'),execution_scope(self.scope):
            model=llm.build_llm({'provider':'openai','api_key':'synthetic-wire-only'})
            with self.assertRaises(llm.ConfigError):
                await model.with_structured_output(lenses.ROUTER_SCHEMA['schema'],method='json_schema').ainvoke([HumanMessage(content='test')])
        self.assertEqual(len(self.wires),1)
        row=await db.pool().fetchrow('SELECT status,actual_usd,input_tokens FROM mra_usage WHERE run_id=$1',db.uid(self.scope.run_id))
        self.assertEqual(row['status'],'complete');self.assertEqual(row['input_tokens'],100)
        self.assertGreater(row['actual_usd'],0)
    async def test_rejected_owner_budget_and_unknown_model_do_not_reserve(self):
        count=await db.pool().fetchval('SELECT count(*) FROM mra_usage')
        with patch.dict(os.environ,{'MRA_OWNER_BUDGET_USD':'0'}),execution_scope(self.scope):
            with self.assertRaises(usage.BudgetError):await usage.reserve('openai','gpt-5-mini',[HumanMessage(content='test')],2048,True)
        with execution_scope(self.scope):
            with self.assertRaises(usage.BudgetError):await usage.reserve('claude','unknown',[HumanMessage(content='test')],2048,True)
        self.assertEqual(await db.pool().fetchval('SELECT count(*) FROM mra_usage'),count)
    async def test_cached_and_live_contexts_do_not_cross(self):
        async def cached():
            with execution_scope(Execution(self.owner,str(uuid.uuid4()),'cached','pricing-comparison')):
                return (await llm.build_llm({'provider':'openai','api_key':'ignored'},'analyst').ainvoke([HumanMessage(content='Override me')])).content
        async def live():
            with execution_scope(self.scope):
                return (await llm.build_llm({'provider':'openai','api_key':'synthetic-wire-only'},'analyst').ainvoke([HumanMessage(content='test')])).content
        with self.sdk():a,b=await asyncio.gather(cached(),live())
        self.assertIn('fictional',a);self.assertIn('Offline',b);self.assertEqual(len(self.wires),1)
        with self.assertRaises(RuntimeError):llm.build_llm({'provider':'openai'})
    async def test_expert_lenses_use_same_provider_and_metered_structured_output(self):
        def response(body):
            schema=body.get('response_format',{}).get('json_schema',{}).get('name','')
            if schema=='lens_selection':return json.dumps({'lenses':[{'id':'ansoff-growth-vectors','why':'Pilot scope','weight':'primary'}],'no_fit':False})
            return json.dumps({'plans':[{'agent':'reviewer','questions':[{'question':'What is the smallest pilot?','via':'Ansoff'}]}]})
        with self.sdk(content=response),patch.object(lenses,'print',create=True),execution_scope(self.scope):
            plan,_=await lenses.prepare_lens_plans([{'id':'reviewer','name':'Vera'}],'pilot','brief',{'provider':'openai','api_key':'synthetic-wire-only'})
        self.assertIn('reviewer',plan);self.assertEqual(len(self.wires),2)
        self.assertTrue(all(w['model']=='gpt-5-mini' for w in self.wires))
        self.assertEqual(lenses.model_label({'provider':'openai','model':'gpt-5-mini'}),self.wires[0]['model'])
        self.assertEqual(lenses.model_label({'provider':'claude'}),'claude-haiku-4-5 / claude-sonnet-5')
        self.assertEqual(lenses.model_label({'provider':'hf','model':'fixture/model'}),'fixture/model')
    async def test_real_graph_custom_transformer_and_stopped_run(self):
        cid=await db.ensure_conversation(self.owner,None,'Synthetic custom graph')
        run=runs.register(cid,self.owner,'mock')
        cfg={'enable_reviewer':True,'enable_client':False,'custom_agents':[{'id':'style','enabled':True,'name':'Style','system_prompt':'Keep concise','mode':'transformer'}],'stage_order':['style','reviewer']}
        run.task=asyncio.create_task(runs.execute_run(run,message='test',raw_files=[],cfg=cfg));await run.task
        nodes=[e['node'] for e in run.events if e['type']=='node_complete']
        self.assertEqual(nodes,['intake','analyst','c_style','reviewer','revise_reviewer'])
        self.assertEqual(run.status,'done')
        cid2=await db.ensure_conversation(self.owner,None,'Synthetic stopped run')
        stopped=runs.register(cid2,self.owner,'mock')
        original=examples.FixtureModel.ainvoke
        async def slow(model,messages):await asyncio.sleep(1);return await original(model,messages)
        with patch.object(examples.FixtureModel,'ainvoke',slow):
            stopped.task=asyncio.create_task(runs.execute_run(stopped,message='test',raw_files=[],cfg={}))
            await asyncio.sleep(.05);stopped.task.cancel()
            with self.assertRaises(asyncio.CancelledError):await stopped.task
            if stopped.cleanup_task:await stopped.cleanup_task
        self.assertEqual(stopped.status,'stopped');self.assertEqual((await db.get_run(self.owner,cid2))['status'],'stopped')
        with self.assertRaises(db.OwnershipError):await db.get_run(self.other,cid2)
    async def test_sse_rechecks_revoked_session_without_request_cache(self):
        cid=await db.ensure_conversation(self.owner,None,'SSE revocation')
        run=runs.Run(cid,self.owner,'mock');await run.emit({'type':'conversation','conversation_id':cid})
        allowed=True
        async def check():return allowed
        tail=runs.tail(run,authorized=check)
        self.assertIn('conversation',await anext(tail))
        allowed=False
        self.assertIn('session_expired',await anext(tail))
        with self.assertRaises(StopAsyncIteration):await anext(tail)
    async def test_pending_upload_reserves_quota_and_private_history_sql(self):
        cid=await db.ensure_conversation(self.owner,None,'Quota test')
        await db.reserve_upload(self.owner,cid,str(uuid.uuid4()),100*1024*1024)
        with self.assertRaises(db.StorageLimitError):await db.reserve_upload(self.owner,cid,str(uuid.uuid4()),1)
        with self.assertRaises(db.OwnershipError):await db.save_upload(self.owner,cid,{'owner_id':self.other})
        for i in range(15):await db.add_message(self.owner,cid,'user',str(i))
        self.assertEqual([m['content'] for m in await db.get_history(self.owner,cid)],list(map(str,range(3,15))))
        with self.assertRaises(db.OwnershipError):await db.add_message(self.other,cid,'user','foreign')
    async def test_retained_trace_bytes_block_next_write_and_dispatch(self):
        cid=await db.ensure_conversation(self.owner,None,'Retained trace budget')
        run=runs.Run(cid,self.owner,'mock')
        await run.finish('done',{'type':'final','output':'x'*1800})
        before=await db.pool().fetchval('SELECT count(*) FROM mra_usage')
        with patch.object(db,'WORKSPACE_DATA_LIMIT',2000):
            with self.assertRaises(db.StorageLimitError):await db.add_message(self.owner,cid,'user','y'*400)
            with execution_scope(self.scope),self.sdk():
                with self.assertRaises(db.StorageLimitError):
                    await llm.build_llm({'provider':'openai','api_key':'synthetic-wire-only'}).ainvoke([HumanMessage(content='test')])
        self.assertFalse(self.wires)
        self.assertEqual(await db.pool().fetchval('SELECT count(*) FROM mra_usage'),before)
        self.assertEqual(await db.get_messages(self.owner,cid),[])
    async def test_database_failure_does_not_fall_back_to_memory(self):
        await db.close_db()
        with self.assertRaises(RuntimeError):await db.ensure_conversation(self.owner,None,'Must not be retained')
        self.assertFalse(db._mem)
    async def test_legacy_unowned_schema_fails_startup_without_adopting_rows(self):
        import asyncpg
        await db.close_db()
        name='mra_legacy_'+uuid.uuid4().hex
        admin=await asyncpg.connect('postgresql://macbook@127.0.0.1:55443/postgres',ssl=False)
        await admin.execute('CREATE DATABASE '+name)
        url='postgresql://macbook@127.0.0.1:55443/'+name
        try:
            legacy=await asyncpg.connect(url,ssl=False)
            await legacy.execute('CREATE TABLE mra_conversations(id UUID PRIMARY KEY,session_id TEXT,title TEXT)')
            await legacy.execute("INSERT INTO mra_conversations VALUES($1,'unowned-test','synthetic legacy row')",uuid.uuid4())
            await legacy.close()
            with patch.dict(os.environ,{'DATABASE_URL':url}):
                with self.assertRaises(asyncpg.UndefinedColumnError):await db.init_db()
            self.assertIsNone(db._pool);self.assertFalse(db._mem)
            verify=await asyncpg.connect(url,ssl=False)
            self.assertEqual(await verify.fetchval('SELECT count(*) FROM mra_conversations'),1)
            self.assertIsNone(await verify.fetchval("SELECT to_regclass('mra_users')"))
            await verify.close()
        finally:
            await admin.execute('DROP DATABASE '+name)
            await admin.close()

class InputAndExport(unittest.TestCase):
    def test_pdf_filter_expansion_is_bounded_and_configuration_restored(self):
        from pypdf import PdfWriter,get_configuration
        from pypdf.generic import DecodedStreamObject,NameObject
        writer=PdfWriter();page=writer.add_blank_page(width=100,height=100)
        stream=DecodedStreamObject();stream.set_data(b' '*(9*1024*1024))
        page[NameObject('/Contents')]=writer._add_object(stream.flate_encode())
        output=io.BytesIO();writer.write(output)
        original=get_configuration()
        with self.assertRaises(ExtractError):extract_file('compressed.pdf',output.getvalue())
        self.assertEqual(get_configuration(),original)
        from app.export import to_pdf
        normal=extract_file('normal.pdf',to_pdf('Normal report','# Evidence\n\nA readable normal PDF.',[]))
        self.assertIn('readable normal PDF',normal['text'])
    def test_zip_expansion_and_image_header_rejected(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:archive.writestr('huge.xml',b'x'*(16*1024*1024))
        with self.assertRaises(ExtractError):extract_file('bad.docx',out.getvalue())
        with self.assertRaises(ExtractError):extract_file('bad.png',b'not a PNG')
    def test_typst_quote_and_raw_delimiters_are_literal_and_root_confined(self):
        import typst
        actual=typst.compile;captured={}
        def compile_file(path,**kwargs):
            captured['source']=Path(path).read_text();captured['root']=kwargs.get('root')
            return actual(path,**kwargs)
        source='Report [source: https://example.com/a";read("/etc/passwd")]\n\n```\n````#read("/etc/passwd")\n```\n'
        with patch.object(typst,'compile',compile_file):data=_pdf_via_typst('Safe title',source,[])
        self.assertTrue(data.startswith(b'%PDF'));self.assertTrue(captured['root'])
        self.assertNotIn('#link("https://example.com/a";',captured['source'])
        # Actual compiler succeeds without a filesystem read or injected Typst expression.
        from pypdf import PdfReader
        text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)
        self.assertNotIn('root:x:',text)
    def test_export_url_scheme_and_payload_bounds(self):
        from app.export import _extract_sources
        text,urls=_extract_sources('[source: file:///etc/passwd] [source: https://example.com]')
        self.assertEqual(urls,['https://example.com']);self.assertIn('unsupported',text)
        with self.assertRaises(ValueError):validate_export({'markdown':'x'*150001})

if __name__=='__main__':unittest.main()
