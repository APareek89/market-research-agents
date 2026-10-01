"""Password accounts, revocable opaque sessions, signed browser CSRF and quotas."""
import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from urllib.parse import urlparse

import asyncpg
import bcrypt
from fastapi import APIRouter, HTTPException, Request, Response
from . import db

router=APIRouter(prefix='/api/auth')
SESSION_COOKIE='mra_session'
CSRF_COOKIE='mra_csrf'
SESSION_SECONDS=7*86400
FIXTURE_USER={'id':'00000000-0000-4000-8000-000000000001','email':'fixture@example.invalid'}
_DUMMY_HASH=bcrypt.hashpw(b'noncredential-comparison-only',bcrypt.gensalt(rounds=12))


def enabled():
    return os.getenv('PORTFOLIO_AUTH_ENABLED','1')!='0'

def origin():
    return os.getenv('PUBLIC_BASE_URL','http://127.0.0.1:8953').rstrip('/')

def initialize():
    if not enabled():
        if not db.fixture_mode():
            raise RuntimeError('Authentication may only be disabled in explicit local fixtures')
        return
    if len(os.getenv('AUTH_SECRET',''))<32:
        raise RuntimeError('AUTH_SECRET must contain at least 32 characters')
    parsed=urlparse(origin())
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.path not in {'','/'} or parsed.username:
        raise RuntimeError('PUBLIC_BASE_URL must be an exact origin')
    if os.getenv('NODE_ENV')=='production' and parsed.scheme!='https':
        raise RuntimeError('Production requires an HTTPS public origin')

def digest(value):
    return hmac.new(os.environ['AUTH_SECRET'].encode(),value.encode(),hashlib.sha256).hexdigest()

def _cookie(response,name,value,seconds):
    response.set_cookie(name,value,max_age=seconds,httponly=True,secure=origin().startswith('https://'),samesite='lax',path='/')

def _binding(request):
    return hashlib.sha256(request.cookies.get(SESSION_COOKIE,'anonymous').encode()).hexdigest()

def issue_csrf(request,response):
    existing=request.cookies.get(CSRF_COOKIE,'')
    if valid_csrf(request,existing):
        return existing
    prefix=f'{int(time.time())}.{secrets.token_hex(24)}'
    token=prefix+'.'+digest('csrf:'+_binding(request)+':'+prefix)
    _cookie(response,CSRF_COOKIE,token,3600)
    return token

def valid_csrf(request,token):
    try:
        if len(token)>200:
            return False
        ts,nonce,signature=token.split('.')
        age=time.time()-int(ts)
        expected=digest('csrf:'+_binding(request)+':'+ts+'.'+nonce)
        return 0<=age<=3600 and len(nonce)==48 and hmac.compare_digest(signature,expected)
    except (ValueError,TypeError):
        return False

def check_csrf(request):
    if not enabled():
        return
    if request.headers.get('origin')!=origin():
        raise HTTPException(403,'Request origin is not allowed')
    if request.headers.get('sec-fetch-site') in {'cross-site','none'}:
        raise HTTPException(403,'Cross-site mutations are not allowed')
    # Concurrent tabs may retain different issued tokens. Each must still be
    # signed for the exact current auth session; identity changes invalidate it.
    if not valid_csrf(request,request.headers.get('x-csrf-token','')):
        raise HTTPException(403,'CSRF token expired; refresh the page')

async def current_user(request):
    if not enabled():
        return FIXTURE_USER
    token=request.cookies.get(SESSION_COOKIE,'')
    if not re.fullmatch(r'[0-9a-f]{64}',token):
        return None
    row=await db.pool().fetchrow('''SELECT u.id,u.email FROM mra_sessions s JOIN mra_users u ON u.id=s.owner_id
        WHERE s.token_hash=$1 AND s.expires_at>now() AND NOT u.disabled''',digest(token))
    return {'id':str(row['id']),'email':row['email']} if row else None

async def require_user(request):
    user=await current_user(request)
    if not user:
        raise HTTPException(401,'Sign in to continue')
    return user

async def session_valid(token,owner_id):
    if not enabled():
        return True
    if not token:
        return False
    return bool(await db.pool().fetchval('''SELECT 1 FROM mra_sessions s JOIN mra_users u ON u.id=s.owner_id
        WHERE s.token_hash=$1 AND s.owner_id=$2 AND s.expires_at>now() AND NOT u.disabled''',digest(token),db.uid(owner_id)))

async def rate(key,limit,seconds):
    if not enabled():
        return
    count=await db.pool().fetchval('''INSERT INTO mra_rates(key,window_start,count) VALUES($1,now(),1)
        ON CONFLICT(key) DO UPDATE SET count=CASE WHEN mra_rates.window_start<now()-($2*interval '1 second') THEN 1 ELSE mra_rates.count+1 END,
        window_start=CASE WHEN mra_rates.window_start<now()-($2*interval '1 second') THEN now() ELSE mra_rates.window_start END RETURNING count''',digest('rate:'+key),seconds)
    if count>limit:
        raise HTTPException(429,'Request limit reached. Please try again later.')

async def limit_action(request,action,limit=30,seconds=900,owner_id=None):
    # Only uvicorn's exact trusted proxy allowlist may rewrite request.client.
    peer=request.client.host if request.client else 'unknown'
    await rate('ip:'+peer+':'+action,limit,seconds)
    if owner_id:
        await rate('owner:'+owner_id+':'+action,limit,seconds)

async def _body(request):
    if request.headers.get('content-type','').split(';')[0]!='application/json':
        raise HTTPException(415,'Expected application/json')
    raw=await request.body()
    if len(raw)>4096:
        raise HTTPException(413,'Credentials payload is too large')
    try:
        body=json.loads(raw)
    except (ValueError,UnicodeDecodeError):
        raise HTTPException(400,'Invalid JSON')
    if not isinstance(body,dict):
        raise HTTPException(400,'Expected an object')
    return body

def _credentials(body):
    email=body.get('email','')
    password=body.get('password','')
    if not isinstance(email,str) or not isinstance(password,str):
        raise HTTPException(400,'Email and password are required')
    email=email.strip().lower()
    if not re.fullmatch(r'[^\s@]{1,100}@[^\s@]{1,150}\.[^\s@]{2,40}',email) or len(email)>254:
        raise HTTPException(400,'Enter a valid email address')
    if len(password)<12 or len(password.encode())>72:
        raise HTTPException(400,'Use at least 12 characters and at most 72 UTF-8 bytes')
    return email,password

async def _session(response,owner_id):
    token=secrets.token_hex(32)
    async with db.pool().acquire() as con,con.transaction():
        await con.execute('SELECT id FROM mra_users WHERE id=$1 FOR UPDATE',db.uid(owner_id))
        await con.execute('DELETE FROM mra_sessions WHERE owner_id=$1 AND expires_at<now()',db.uid(owner_id))
        if await con.fetchval('SELECT count(*) FROM mra_sessions WHERE owner_id=$1',db.uid(owner_id))>=20:
            raise HTTPException(429,'Too many active sessions; sign out another browser first')
        await con.execute("INSERT INTO mra_sessions(token_hash,owner_id,expires_at) VALUES($1,$2,now()+($3*interval '1 second'))",digest(token),db.uid(owner_id),SESSION_SECONDS)

    _cookie(response,SESSION_COOKIE,token,SESSION_SECONDS)
    response.delete_cookie(CSRF_COOKIE,path='/')

@router.get('/session')
async def session(request:Request,response:Response):
    response.headers['Cache-Control']='no-store'
    return {'enabled':enabled(),'user':await current_user(request) if enabled() else FIXTURE_USER,'csrf_token':issue_csrf(request,response) if enabled() else ''}

@router.post('/signup',status_code=201)
async def signup(request:Request,response:Response):
    check_csrf(request)
    if not enabled():
        raise HTTPException(409,'Accounts are disabled for fixtures')
    await limit_action(request,'auth',15)
    email,password=_credentials(await _body(request))
    encoded=(await asyncio.to_thread(bcrypt.hashpw,password.encode(),bcrypt.gensalt(rounds=12))).decode()
    owner=str(uuid.uuid4())
    try:
        async with db.pool().acquire() as con,con.transaction():
            await con.execute('SELECT pg_advisory_xact_lock(74432003)')
            if await con.fetchval('SELECT count(*) FROM mra_users')>=1000:
                raise HTTPException(503,'Account capacity reached')
            await con.execute('INSERT INTO mra_users(id,email,password_hash) VALUES($1,$2,$3)',db.uid(owner),email,encoded)
    except asyncpg.UniqueViolationError:
        raise HTTPException(409,'An account already exists; sign in instead')
    await _session(response,owner)
    return {'ok':True,'user':{'id':owner,'email':email}}

@router.post('/signin')
async def signin(request:Request,response:Response):
    check_csrf(request)
    await limit_action(request,'auth',15)
    email,password=_credentials(await _body(request))
    await rate('login:'+email,15,900)
    row=await db.pool().fetchrow('SELECT id,password_hash,disabled FROM mra_users WHERE email=$1',email)
    valid=await asyncio.to_thread(bcrypt.checkpw,password.encode(),row['password_hash'].encode() if row else _DUMMY_HASH)
    if not row or not valid or row['disabled']:
        raise HTTPException(401,'Email or password is incorrect')
    await _session(response,str(row['id']))
    return {'ok':True,'user':{'id':str(row['id']),'email':email}}

@router.post('/signout')
async def signout(request:Request,response:Response):
    check_csrf(request)
    token=request.cookies.get(SESSION_COOKIE,'')
    if enabled() and token:
        await db.pool().execute('DELETE FROM mra_sessions WHERE token_hash=$1',digest(token))
    response.delete_cookie(SESSION_COOKIE,path='/')
    response.delete_cookie(CSRF_COOKIE,path='/')
    return {'ok':True}
