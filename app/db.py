"""Owner-scoped PostgreSQL persistence; memory is an explicit local fixture only."""
import datetime
import json
import os
import ssl
import uuid
from pathlib import Path
from urllib.parse import urlparse
import asyncpg

_pool: asyncpg.Pool | None = None
_mem: dict[str, dict] = {}
_mem_runs: dict[str, dict] = {}
WORKSPACE_DATA_LIMIT = 50*1024*1024
APP_DATA_LIMIT = 1024*1024*1024

class OwnershipError(Exception):
    pass

class StorageLimitError(Exception):
    pass

def fixture_mode():
    return os.getenv('MRA_STORAGE_MODE') == 'fixture' and os.getenv('PORTFOLIO_AUTH_ENABLED') == '0' and os.getenv('NODE_ENV') != 'production'

def pool():
    if _pool is None:
        raise RuntimeError('Private database is unavailable')
    return _pool

def uid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise OwnershipError('Resource not found') from exc

async def init_db():
    global _pool
    if fixture_mode():
        return 'fixture'
    url = os.getenv('DATABASE_URL', '')
    if not url:
        raise RuntimeError('DATABASE_URL is required')
    if os.getenv('DATABASE_SSL') == 'disable':
        if urlparse(url).hostname not in {'localhost','127.0.0.1','::1'} or os.getenv('NODE_ENV') == 'production':
            raise RuntimeError('Plaintext PostgreSQL is limited to local fixtures')
        tls = False
    else:
        ca = os.getenv('DATABASE_SSL_CA_FILE')
        if not ca:
            raise RuntimeError('A PostgreSQL CA file is required')
        tls = ssl.create_default_context(cafile=ca)
    candidate = await asyncpg.create_pool(url, ssl=tls, min_size=1, max_size=6, timeout=10, command_timeout=15)
    try:
        async with candidate.acquire() as con:
            await con.execute((Path(__file__).parent/'migrations/001_portfolio.sql').read_text())
            await con.execute("UPDATE mra_runs SET status='error',updated_at=now() WHERE status='running'")
    except BaseException:
        await candidate.close()
        raise
    _pool = candidate
    return 'postgres'

async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None

async def require_conversation(owner_id, conversation_id):
    owner, cid = uid(owner_id), uid(conversation_id)
    if fixture_mode():
        if _mem.get(str(cid), {}).get('owner_id') != str(owner):
            raise OwnershipError('Resource not found')
        return
    if not await pool().fetchval('SELECT 1 FROM mra_conversations WHERE id=$1 AND owner_id=$2', cid, owner):
        raise OwnershipError('Resource not found')

async def ensure_conversation(owner_id, conversation_id, title_hint):
    if conversation_id:
        await require_conversation(owner_id, conversation_id)
        return str(uid(conversation_id))
    cid, owner = str(uuid.uuid4()), uid(owner_id)
    title = (title_hint or 'New research')[:80]
    if fixture_mode():
        _mem[cid] = {'owner_id':str(owner),'title':title,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'messages':[]}
    else:
        async with pool().acquire() as con, con.transaction():
            await con.execute('SELECT id FROM mra_users WHERE id=$1 FOR UPDATE', owner)
            if await con.fetchval('SELECT count(*) FROM mra_conversations WHERE owner_id=$1', owner) >= 200:
                raise StorageLimitError('Workspace conversation limit reached')
            await con.execute('INSERT INTO mra_conversations(id,owner_id,title) VALUES($1,$2,$3)',uid(cid),owner,title)
    return cid

async def check_workspace(owner_id, con=None, extra=0):
    if fixture_mode():
        return
    con = con or pool()
    own = await con.fetchval("SELECT (SELECT coalesce(sum(octet_length(content)+octet_length(coalesce(trace::text,''))),0) FROM mra_messages WHERE owner_id=$1)+(SELECT coalesce(sum(octet_length(events::text)),0) FROM mra_runs WHERE owner_id=$1)",uid(owner_id))
    if own + extra > WORKSPACE_DATA_LIMIT:
        raise StorageLimitError('Workspace report storage limit reached')
    total = await con.fetchval("SELECT (SELECT coalesce(sum(octet_length(content)+octet_length(coalesce(trace::text,''))),0) FROM mra_messages)+(SELECT coalesce(sum(octet_length(events::text)),0) FROM mra_runs)")
    if total + extra > APP_DATA_LIMIT:
        raise StorageLimitError('Application report storage is full')

async def add_message(owner_id, conversation_id, role, content, trace=None):
    await require_conversation(owner_id,conversation_id)
    encoded = json.dumps(trace) if trace else None
    if role not in {'user','assistant'} or len(content)>200000 or len(encoded or '')>1500000:
        raise StorageLimitError('Report is too large to persist')
    mid = str(uuid.uuid4())
    if fixture_mode():
        _mem[conversation_id]['messages'].append({'id':mid,'role':role,'content':content,'trace':trace,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        return
    async with pool().acquire() as con, con.transaction():
        await con.execute('SELECT pg_advisory_xact_lock(74432001)')
        await check_workspace(owner_id,con,len(content.encode())+len((encoded or '').encode()))
        await con.execute('INSERT INTO mra_messages(id,conversation_id,owner_id,role,content,trace) VALUES($1,$2,$3,$4,$5,$6)',uid(mid),uid(conversation_id),uid(owner_id),role,content,encoded)

async def save_run(run, *, events=None, status=None):
    await require_conversation(run.owner_id,run.conversation_id)
    events = run.events if events is None else events
    encoded = json.dumps(events)
    if len(events)>100 or len(encoded.encode())>2*1024*1024:
        raise StorageLimitError('Run trace limit reached')
    if fixture_mode():
        _mem_runs[run.conversation_id]={'id':run.id,'owner_id':run.owner_id,'status':status or run.status,'events':json.loads(encoded)}
        return
    async with pool().acquire() as con,con.transaction():
        await con.execute('SELECT pg_advisory_xact_lock(74432001)')
        old=await con.fetchval('SELECT octet_length(events::text) FROM mra_runs WHERE id=$1 AND owner_id=$2',uid(run.id),uid(run.owner_id)) or 0
        await check_workspace(run.owner_id,con,max(0,len(encoded.encode())-old))
        result=await con.execute('INSERT INTO mra_runs(id,conversation_id,owner_id,status,events) VALUES($1,$2,$3,$4,$5)\n          ON CONFLICT(id) DO UPDATE SET status=EXCLUDED.status,events=EXCLUDED.events,updated_at=now()\n          WHERE mra_runs.owner_id=EXCLUDED.owner_id AND mra_runs.conversation_id=EXCLUDED.conversation_id',uid(run.id),uid(run.conversation_id),uid(run.owner_id),status or run.status,encoded)
        if result.endswith(' 0'):
            raise OwnershipError('Resource not found')

async def get_run(owner_id,conversation_id):
    await require_conversation(owner_id,conversation_id)
    if fixture_mode():
        return _mem_runs.get(conversation_id)
    r = await pool().fetchrow('SELECT id,status,events FROM mra_runs WHERE conversation_id=$1 AND owner_id=$2 ORDER BY created_at DESC LIMIT 1',uid(conversation_id),uid(owner_id))
    return {'id':str(r['id']),'status':r['status'],'events':json.loads(r['events'])} if r else None

async def get_messages(owner_id,conversation_id):
    await require_conversation(owner_id,conversation_id)
    if fixture_mode():
        return list(_mem[conversation_id]['messages'])
    rows=await pool().fetch('SELECT id,role,content,trace,created_at FROM mra_messages WHERE conversation_id=$1 AND owner_id=$2 ORDER BY created_at',uid(conversation_id),uid(owner_id))
    return [{'id':str(r['id']),'role':r['role'],'content':r['content'],'trace':json.loads(r['trace']) if r['trace'] else None,'created_at':r['created_at'].isoformat()} for r in rows]

async def get_history(owner_id,conversation_id,limit=12):
    await require_conversation(owner_id,conversation_id)
    limit=max(1,min(12,limit))
    if fixture_mode():
        return [{'role':m['role'],'content':m['content']} for m in _mem[conversation_id]['messages'][-limit:]]
    rows=await pool().fetch('SELECT role,content FROM mra_messages WHERE owner_id=$1 AND conversation_id=$2 ORDER BY created_at DESC LIMIT $3',uid(owner_id),uid(conversation_id),limit)
    return [dict(r) for r in reversed(rows)]

async def list_conversations(owner_id):
    if fixture_mode():
        return [{'id':cid,**{k:c[k] for k in ('title','created_at')}} for cid,c in _mem.items() if c['owner_id']==owner_id]
    rows=await pool().fetch('SELECT id,title,created_at FROM mra_conversations WHERE owner_id=$1 ORDER BY created_at DESC LIMIT 100',uid(owner_id))
    return [{'id':str(r['id']),'title':r['title'],'created_at':r['created_at'].isoformat()} for r in rows]

async def check_upload_quota(owner_id,extra,con=None):
    if fixture_mode():
        return
    con=con or pool()
    own=await con.fetchval('SELECT coalesce(sum(bytes),0) FROM mra_uploads WHERE owner_id=$1',uid(owner_id))
    total=await con.fetchval('SELECT coalesce(sum(bytes),0) FROM mra_uploads')
    if own+extra>100*1024*1024 or total+extra>1024*1024*1024:
        raise StorageLimitError('Upload storage limit reached')

async def reserve_upload(owner_id,conversation_id,upload_id,size):
    if conversation_id:
        await require_conversation(owner_id,conversation_id)
    if fixture_mode():
        return
    async with pool().acquire() as con,con.transaction():
        await con.execute('SELECT pg_advisory_xact_lock(74432002)')
        await check_upload_quota(owner_id,size,con)
        await con.execute("INSERT INTO mra_uploads(id,owner_id,conversation_id,bytes,storage_ref) VALUES($1,$2,$3,$4,'{}')",uid(upload_id),uid(owner_id),uid(conversation_id) if conversation_id else None,size)

async def save_upload(owner_id,conversation_id,ref):
    if str(uid(ref.get('owner_id'))) != str(uid(owner_id)):
        raise OwnershipError('Upload owner does not match')
    if fixture_mode():
        return
    result=await pool().execute("UPDATE mra_uploads SET storage_ref=$1 WHERE id=$2 AND owner_id=$3 AND bytes=$4 AND conversation_id IS NOT DISTINCT FROM $5 AND storage_ref='{}'::jsonb",json.dumps(ref),uid(ref['upload_id']),uid(owner_id),ref['bytes'],uid(conversation_id) if conversation_id else None)
    if result!='UPDATE 1':
        raise OwnershipError('Upload reservation not found')

async def get_upload(owner_id,upload_id):
    r=await pool().fetchval('SELECT storage_ref FROM mra_uploads WHERE id=$1 AND owner_id=$2',uid(upload_id),uid(owner_id))
    if not r or r=='{}':
        raise OwnershipError('Resource not found')
    return json.loads(r)

# Framework content is curated, shared reference material, never user input.
async def fetch_framework_index(roles):
    if not _pool:
        return []
    try:
        return [dict(r) for r in await _pool.fetch('SELECT id,name,when_to_use,trigger_signals,reviewer FROM mra_frameworks WHERE reviewer && $1::text[]',roles)]
    except asyncpg.UndefinedTableError:
        return []

async def fetch_frameworks(ids):
    if not _pool or not ids:
        return []
    try:
        return [dict(r) for r in await _pool.fetch('SELECT id,name,cluster,when_to_use,reviewer,body_md FROM mra_frameworks WHERE id=ANY($1::text[])',ids)]
    except asyncpg.UndefinedTableError:
        return []

async def count_frameworks():
    if not _pool:
        return 0
    try:
        return await _pool.fetchval('SELECT count(*) FROM mra_frameworks')
    except asyncpg.UndefinedTableError:
        return 0
