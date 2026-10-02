"""Authenticated council API; detached runs remain durable and owner-scoped."""
import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from . import auth,db,runs,examples,kb
from .export import pdf_engine,to_pdf,to_pptx,validate_export
from .extract import extract_file,ExtractError,MAX_FILE_BYTES
from .graph import MAX_CUSTOM_AGENTS
from .llm import ConfigError,build_llm,DEFAULT_AGENT_MODELS,HF_MODELS,default_provider,default_model,server_key_available
from .prompts import CLAUDE_MODELS,DEFAULT_AGENTS,EXPERT_AGENTS,OPENAI_MODELS,PROMPTS_VERSION
from .execution import Execution,execution_scope

@asynccontextmanager
async def lifespan(app):
    auth.initialize()
    app.state.db_mode=await db.init_db()
    if not db.fixture_mode():
        async with db.pool().acquire() as con:
            await kb.ingest(con)
    app.state.frameworks_available=await db.count_frameworks()
    yield
    for run in list(runs.RUNS.values()):
        if run.task and not run.task.done():run.task.cancel()
    await db.close_db()

app=FastAPI(title='Market Research Agent Council',lifespan=lifespan)
app.include_router(auth.router)

class LimitedBody:
    """Bound request bytes before Starlette multipart parsing or JSON buffering."""
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope.get('method') not in {'POST','PUT','PATCH'}:
            return await self.app(scope,receive,send)
        maximum=32*1024*1024 if scope.get('path') in {'/api/chat','/api/synthesize-prompt'} else 9*1024*1024
        headers=dict(scope.get('headers',[]))
        try:size=int(headers.get(b'content-length',b'0'))
        except ValueError:size=maximum+1
        if size>maximum:
            return await JSONResponse({'error':'Request body is too large'},413)(scope,receive,send)
        parts=[];total=0
        while True:
            part=await receive()
            if part['type']=='http.disconnect':return
            data=part.get('body',b'');total+=len(data)
            if total>maximum:
                return await JSONResponse({'error':'Request body is too large'},413)(scope,receive,send)
            parts.append(data)
            if not part.get('more_body',False):break
        body=b''.join(parts);del parts
        delivered=False
        async def bounded_receive():
            nonlocal delivered,body
            if not delivered:
                delivered=True
                value=body;body=b''
                return {'type':'http.request','body':value,'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)

app.add_middleware(LimitedBody)
_INPUT_SLOTS=asyncio.Semaphore(2)

@app.middleware('http')
async def access(request:Request,call_next):
    try:
        if request.url.path.startswith('/api/'):
            if request.method not in {'GET','HEAD','OPTIONS'}:auth.check_csrf(request)
            if not request.url.path.startswith('/api/auth/'):
                request.state.user=await auth.require_user(request)
                await auth.limit_action(request,'api',600,900,request.state.user['id'])
        if request.method=='POST' and request.url.path in {'/api/chat','/api/synthesize-prompt','/api/export'}:
            try:await asyncio.wait_for(_INPUT_SLOTS.acquire(),.1)
            except asyncio.TimeoutError:raise HTTPException(429,'Two large requests are already being processed; try again shortly')
            try:response=await call_next(request)
            finally:_INPUT_SLOTS.release()
        else:
            response=await call_next(request)
    except HTTPException as exc:
        response=JSONResponse({'error':exc.detail,'detail':exc.detail},exc.status_code)
    except db.OwnershipError:
        response=JSONResponse({'error':'Resource not found'},404)
    except db.StorageLimitError as exc:
        response=JSONResponse({'error':str(exc)},429)
    except (ConfigError,ExtractError,ValueError) as exc:
        response=JSONResponse({'error':str(exc)},400)
    except Exception:
        response=JSONResponse({'error':'Service unavailable; no automatic retry was made'},503)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Frame-Options']='DENY'
    if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    return response

@app.get('/healthz')
async def health():
    if not db.fixture_mode():await db.pool().fetchval('SELECT 1')
    return {'ok':True,'auth':auth.enabled(),'mock':os.getenv('MRA_MOCK_MODE')=='1'}

SSE_HEADERS={'Cache-Control':'no-store','X-Accel-Buffering':'no'}
def sse(obj):return f'data: {json.dumps(obj)}\n\n'

def error_stream(message):
    async def gen():yield sse({'type':'error','message':message})
    return StreamingResponse(gen(),media_type='text/event-stream',headers=SSE_HEADERS)

@app.get('/api/defaults')
async def defaults():
    return {'agents':DEFAULT_AGENTS,'expert_agents':EXPERT_AGENTS,'frameworks_available':getattr(app.state,'frameworks_available',0),'pdf_engine':pdf_engine(),'prompts_version':PROMPTS_VERSION,
      'models':{'claude':CLAUDE_MODELS,'openai':OPENAI_MODELS,'hf':HF_MODELS},'default_model':default_model(),'agent_model_defaults':DEFAULT_AGENT_MODELS,'max_custom_agents':MAX_CUSTOM_AGENTS,
      'default_provider':default_provider(),'server_key_available':server_key_available(),'provider_mode':'mock' if os.getenv('MRA_MOCK_MODE')=='1' else 'live','db':getattr(app.state,'db_mode','unknown')}

@app.get('/api/conversations')
async def conversations(request:Request,session_id:str=''):
    return await db.list_conversations(request.state.user['id'])

@app.get('/api/conversations/{conversation_id}/messages')
async def messages(request:Request,conversation_id:str):
    return await db.get_messages(request.state.user['id'],conversation_id)

def validate_config(raw):
    if len(raw.encode())>100000:raise ValueError('Configuration is too large')
    try:cfg=json.loads(raw or '{}')
    except ValueError:raise ValueError('Invalid configuration JSON')
    if not isinstance(cfg,dict):raise ValueError('Configuration must be an object')
    agents=cfg.get('agents') or {};custom=cfg.get('custom_agents') or [];settings=cfg.get('settings') or {}
    if not isinstance(agents,dict) or not isinstance(custom,list) or len(custom)>3 or not isinstance(settings,dict):raise ValueError('Invalid agent configuration')
    for flag in ('enable_reviewer','enable_client'):
        if flag in cfg and type(cfg[flag]) is not bool:raise ValueError('Review switches must be true or false')
    for agent in [*agents.values(),*custom]:
        if not isinstance(agent,dict):raise ValueError('Invalid agent configuration')
        for field,cap in [('name',80),('system_prompt',12000),('model',160)]:
            if field in agent and (not isinstance(agent[field],str) or len(agent[field])>cap):raise ValueError('Agent field is too large')
        for flag in ('enabled','expert_mode'):
            if flag in agent and type(agent[flag]) is not bool:raise ValueError('Agent switches must be true or false')
        if 'mode' in agent and agent['mode'] not in ('reviewer','transformer'):raise ValueError('Invalid custom stage mode')
    ids=[str(c.get('id','')) for c in custom]
    if len(set(ids))!=len(ids) or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',i) or i in {'reviewer','client','intake','analyst'} for i in ids):raise ValueError('Custom agent IDs must be unique')
    order=cfg.get('stage_order') or []
    if not isinstance(order,list) or len(order)>5 or any(not isinstance(k,str) for k in order) or len(set(order))!=len(order):raise ValueError('Invalid stage order')
    for k,cap in [('api_key',1024),('model',160),('provider',20)]:
        if k in settings and (not isinstance(settings[k],str) or len(settings[k])>cap):raise ValueError('Invalid provider settings')
    # Server execution/proof/fixture markers never come from request JSON.
    return {k:cfg[k] for k in ('agents','custom_agents','settings','stage_order','enable_reviewer','enable_client') if k in cfg}

_EXTRACT=asyncio.Semaphore(2)
async def read_uploads(files):
    if len(files)>8:raise HTTPException(413,'Attach at most eight files')
    raw=[];total=0
    for f in files:
        name=(f.filename or 'file').replace('\\','/').split('/')[-1]
        if not name or len(name)>180 or any(ord(c)<32 for c in name):raise ValueError('Invalid filename')
        data=await f.read(MAX_FILE_BYTES+1);await f.close();total+=len(data)
        if len(data)>MAX_FILE_BYTES or total>30*1024*1024:raise HTTPException(413,'Upload size limit exceeded')
        async with _EXTRACT:await asyncio.to_thread(extract_file,name,data)
        raw.append((name,data))
    return raw

async def persist_files(owner,cid,files):
    from .upload_storage import persist_upload
    refs=[]
    for name,data in files:
        upload_id=str(uuid.uuid4())
        # Pending reservations remain counted on storage errors: no invisible orphan quota.
        await db.reserve_upload(owner,cid,upload_id,len(data))
        ref=await asyncio.to_thread(persist_upload,owner,upload_id,name,data,'application/octet-stream')
        await db.save_upload(owner,cid,ref)
        refs.append({'id':upload_id,'filename':name,'bytes':len(data)})
    return refs

async def begin(owner,cid,message,files,cfg,mode,example_id=None):
    await db.check_workspace(owner,extra=2*1024*1024)
    if not db.fixture_mode() and await db.pool().fetchval('SELECT count(*) FROM mra_runs WHERE owner_id=$1',db.uid(owner))>=500:
        raise db.StorageLimitError('Workspace run limit reached')
    cid=await db.ensure_conversation(owner,cid or None,message or (files[0][0] if files else 'New research'))
    run=runs.register(cid,owner,mode,example_id)
    try:
        refs=await persist_files(owner,cid,files)
        await run.emit({'type':'conversation','conversation_id':cid,'run_id':run.id,'cached':mode=='cached','uploads':refs})
        run.task=asyncio.create_task(runs.execute_run(run,message=message,raw_files=files,cfg=cfg))
        return run
    except BaseException:
        run.status='error';run._notify()
        raise

def authorized(request,owner):
    token=request.cookies.get(auth.SESSION_COOKIE,'')
    return lambda:auth.session_valid(token,owner)

@app.post('/api/chat')
async def chat(request:Request,message:str=Form(''),session_id:str=Form(''),conversation_id:str=Form(''),config:str=Form('{}'),files:list[UploadFile]=File(default=[])):
    owner=request.state.user['id'];await auth.limit_action(request,'research',30,3600,owner)
    if len(message)>30000:raise ValueError('Research question is too long')
    cfg=validate_config(config)
    if conversation_id:await db.require_conversation(owner,conversation_id)
    raw=await read_uploads(files)
    if not message.strip() and not raw:return error_stream('Type a message or attach a file.')
    run=await begin(owner,conversation_id,message.strip(),raw,cfg,'mock' if os.getenv('MRA_MOCK_MODE')=='1' else 'live')
    return StreamingResponse(runs.tail(run,0,authorized(request,owner)),media_type='text/event-stream',headers=SSE_HEADERS)

@app.get('/api/examples')
async def example_list():return examples.listing()

@app.post('/api/examples/{example_id}')
async def example_start(request:Request,example_id:str):
    item=examples.EXAMPLES.get(example_id)
    if item is None:raise HTTPException(404,'Example not found')
    owner=request.state.user['id'];await auth.limit_action(request,'example',10,3600,owner)
    run=await begin(owner,'',item['prompt'],[],examples.config(),'cached',example_id)
    return {'conversation_id':run.conversation_id,'run_id':run.id,'cached':True}

@app.get('/api/runs/active')
async def active(request:Request,session_id:str=''):return runs.active_for(request.state.user['id'])

@app.get('/api/runs/{conversation_id}/stream')
async def stream(request:Request,conversation_id:str,after:int=0):
    owner=request.state.user['id'];await db.require_conversation(owner,conversation_id)
    if after<0 or after>100:raise ValueError('Invalid replay cursor')
    check=authorized(request,owner);run=runs.get(conversation_id,owner)
    if run:return StreamingResponse(runs.tail(run,after,check),media_type='text/event-stream',headers=SSE_HEADERS)
    stored=await db.get_run(owner,conversation_id)
    if not stored:return error_stream('No run found for this conversation.')
    async def replay():
        for event in stored['events'][after:]:
            if not await check():return
            yield sse(event)
    return StreamingResponse(replay(),media_type='text/event-stream',headers=SSE_HEADERS)

@app.post('/api/runs/{conversation_id}/stop')
async def stop(request:Request,conversation_id:str):
    owner=request.state.user['id'];await db.require_conversation(owner,conversation_id)
    run=runs.get(conversation_id,owner)
    if not run or run.status!='running' or not run.task:return {'ok':False,'status':run.status if run else 'none'}
    run.task.cancel();return {'ok':True}

@app.get('/api/uploads/{upload_id}')
async def download(request:Request,upload_id:str):
    from .upload_storage import hydrate_upload
    owner=request.state.user['id'];ref=await db.get_upload(owner,upload_id)
    data=await asyncio.to_thread(hydrate_upload,owner,ref)
    return Response(data,media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="research-upload"','Cache-Control':'private, no-store'})

SYNTH_SYSTEM = """You are an expert prompt engineer for a multi-agent market-research review pipeline.
Your job: rewrite ONE agent's system prompt so the agent emulates a real person the user describes (their boss, client, a domain expert) — from the user's notes and any uploaded documents (reviews they wrote, emails, feedback threads).

Rules:
- Extract the person's priorities, evaluation style, tone, recurring pet peeves, favorite frameworks, and standards of evidence from the material. Quote-worthy phrases they actually use are gold — work them in.
- PRESERVE the pipeline mechanics of the current prompt: what the agent receives, whether it gives feedback vs rewrites, and any output-format contract. The agent must stay compatible with its slot in the pipeline.
- Keep it under 450 words, imperative voice, structured (role, focus areas, concrete instructions, output format).
- If the material is thin, still produce the best prompt you can from what's there plus the current prompt.
- Output ONLY the new system prompt text. No preamble, no commentary, no code fences."""


@app.post('/api/synthesize-prompt')
async def synthesize_prompt(request:Request,agent_name:str=Form(''),agent_role:str=Form(''),current_prompt:str=Form(''),notes:str=Form(''),settings:str=Form('{}'),files:list[UploadFile]=File(default=[])):
    owner=request.state.user['id'];await auth.limit_action(request,'synthesis',15,3600,owner)
    if max(len(current_prompt),len(notes))>12000 or max(len(agent_name),len(agent_role))>100:raise ValueError('Prompt material is too long')
    cfg=validate_config(json.dumps({'settings':json.loads(settings)}))
    raw=await read_uploads(files)
    if not notes.strip() and not raw:raise ValueError('Add notes or upload a document first')
    await persist_files(owner,None,raw)
    parts=[];images=[]
    for name,data in raw:
        async with _EXTRACT:ext=await asyncio.to_thread(extract_file,name,data)
        if ext['kind']=='image':images.append(ext['data_url'])
        else:parts.append(f"--- {name} ---\n{ext['text']}")
    text=f"AGENT: {agent_name} — {agent_role}\nCURRENT SYSTEM PROMPT:\n{current_prompt}\nNOTES:\n{notes}\nUPLOADED MATERIAL:\n"+'\n'.join(parts)
    from langchain_core.messages import HumanMessage,SystemMessage
    from .graph import _text_of
    with execution_scope(Execution(owner,str(uuid.uuid4()),'mock' if os.getenv('MRA_MOCK_MODE')=='1' else 'live')):
        model=build_llm(cfg.get('settings',{}),'analyst')
        response=await model.ainvoke([SystemMessage(content=SYNTH_SYSTEM),HumanMessage(content=[{'type':'text','text':text}]+[{'type':'image_url','image_url':{'url':url}} for url in images])])
    return {'prompt':_text_of(response).strip()}

_EXPORT=asyncio.Semaphore(1)
@app.post('/api/export')
async def export_report(request:Request,payload:dict):
    await auth.limit_action(request,'export',30,3600,request.state.user['id'])
    fmt,title,markdown,diagrams=validate_export(payload)
    async with _EXPORT:
        data=await asyncio.to_thread(to_pptx if fmt=='pptx' else to_pdf,title,markdown,diagrams)
    if len(data)>20*1024*1024:raise ValueError('Export is too large')
    return Response(data,media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation' if fmt=='pptx' else 'application/pdf',headers={'Content-Disposition':f'attachment; filename="agent-council-report.{fmt}"'})

# ---- bot access: let AI assistants (Claude chat etc.) read this site ----
ROBOTS_TXT = """User-agent: *
Allow: /

User-agent: Claude-User
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: anthropic-ai
Allow: /
"""

LLMS_TXT = """# Agent Council
> A 4-agent AI market-research council: Scout (intake) -> Astra (analyst with web
> search) -> Vera (first-principles reviewer, optional Expert Mode with dynamic
> framework lenses) -> Cleo (client/customer reviewer). Reviewed output is
> visibly sharper than a single-shot answer. Reports render tables and mermaid
> diagrams and export to styled PDF (Typst engine) and PPTX.

## App
- Chat UI at / (React SPA; requires JavaScript)
- GET /api/defaults: agents, prompts, models, framework count, PDF engine
- POST /api/chat: multipart (message, session_id, config) -> SSE stream of the
  council run; runs persist server-side and are re-attachable
- GET /api/runs/{conversation_id}/stream: re-attach to a live run
- POST /api/export: {format: pdf|pptx, title, markdown} -> styled report file

Built with FastAPI + LangGraph + Claude models. Source: github.com/APareek89/market-research-agents
"""


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return ROBOTS_TXT


@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms():
    return LLMS_TXT


# ---- static frontend (built React app) ----
DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="static")
else:
    @app.get("/")
    async def root():
        return JSONResponse({"status": "API up. Frontend not built — run `npm run build` in frontend/."})
