"""Atomic, conservative per-owner and shared-key spend reservations."""
import json
import os
import uuid
from decimal import Decimal
from . import db
from .execution import current_execution

# Official standard pricing (USD/million tokens); unknown shared prices fail closed.
CACHE_PRICES={'gpt-5-mini':Decimal('.025'),'gpt-5':Decimal('.125'),'gpt-5.1':Decimal('.125')}
PRICES={('openai','gpt-5-mini'):(Decimal('.25'),Decimal('2')),
        ('openai','gpt-5'):(Decimal('1.25'),Decimal('10')),
        ('openai','gpt-5.1'):(Decimal('1.25'),Decimal('10'))}

class BudgetError(Exception):pass

def bounded_cost(provider,model,messages,max_tokens,shared):
    price=PRICES.get((provider,model))
    if shared and not price:
        raise BudgetError('This server model has no verified price; use an available preset')
    # UTF-8 bytes upper-bound text token count; encoded multimodal input is deliberately conservative.
    size=len(json.dumps([getattr(m,'content','') for m in messages],ensure_ascii=False).encode())+4096
    if size>2*1024*1024:
        raise BudgetError('Model context is too large; shorten the input')
    return (Decimal(size)*price[0]+Decimal(max_tokens)*price[1])/1000000 if price else Decimal(0)

async def reserve(provider,model,messages,max_tokens,shared):
    scope=current_execution()
    if scope.mode not in {'live','proof'}:
        raise BudgetError('Paid dispatch is disabled in this execution')
    cost=bounded_cost(provider,model,messages,max_tokens,shared)
    reservation=str(uuid.uuid4())
    async with db.pool().acquire() as con,con.transaction():
        await con.execute('SELECT pg_advisory_xact_lock(74432004)')
        await db.check_workspace(scope.owner_id,con,extra=2*1024*1024)
        if await con.fetchval('SELECT count(*) FROM mra_usage WHERE run_id=$1',db.uid(scope.run_id))>=36:
            raise BudgetError('Run provider-call limit reached')
        if await con.fetchval('SELECT count(*) FROM mra_usage')>=100000:
            raise BudgetError('Application request ledger is full; prepared examples remain available')
        own=await con.fetchval("SELECT coalesce(sum(coalesce(actual_usd,reserved_usd)),0) FROM mra_usage WHERE owner_id=$1 AND shared",db.uid(scope.owner_id))
        total=await con.fetchval('SELECT coalesce(sum(coalesce(actual_usd,reserved_usd)),0) FROM mra_usage WHERE shared')
        if shared and own+cost>Decimal(os.getenv('MRA_OWNER_BUDGET_USD','.10')):
            raise BudgetError('Your included research budget is used; prepared examples remain available')
        if shared and total+cost>Decimal(os.getenv('MRA_SHARED_BUDGET_USD','.25')):
            raise BudgetError('The shared research budget is used; prepared examples remain available')
        # All rejection checks precede any ledger mutation.
        await con.execute("INSERT INTO mra_usage(id,owner_id,run_id,provider,model,shared,reserved_usd,status) VALUES($1,$2,$3,$4,$5,$6,$7,'reserved')",db.uid(reservation),db.uid(scope.owner_id),db.uid(scope.run_id),provider,model,shared,cost)
    return reservation

async def settle(reservation,provider,model,response):
    scope=current_execution()
    usage=getattr(response,'usage_metadata',None) or {}
    incoming=usage.get('input_tokens')
    outgoing=usage.get('output_tokens')
    if not isinstance(incoming,int) or not isinstance(outgoing,int) or min(incoming,outgoing)<0:
        await db.pool().execute("UPDATE mra_usage SET status='usage_unavailable' WHERE id=$1 AND owner_id=$2 AND run_id=$3",db.uid(reservation),db.uid(scope.owner_id),db.uid(scope.run_id))
        return
    price=PRICES.get((provider,model))
    cached=(usage.get('input_token_details') or {}).get('cache_read',0)
    cached=max(0,min(incoming,cached)) if isinstance(cached,int) else 0
    reasoning=(usage.get('output_token_details') or {}).get('reasoning',0)
    reasoning=max(0,min(outgoing,reasoning)) if isinstance(reasoning,int) else 0
    actual=(Decimal(incoming-cached)*price[0]+Decimal(cached)*CACHE_PRICES.get(model,price[0])+Decimal(outgoing)*price[1])/1000000 if price else None
    await db.pool().execute("UPDATE mra_usage SET actual_usd=$2,input_tokens=$3,output_tokens=$4,status='complete',cached_input_tokens=$7,reasoning_output_tokens=$8 WHERE id=$1 AND owner_id=$5 AND run_id=$6",db.uid(reservation),actual,incoming,outgoing,db.uid(scope.owner_id),db.uid(scope.run_id),cached,reasoning)

async def failed(reservation):
    scope=current_execution()
    # Known successful usage is not overwritten by a later parsing failure.
    await db.pool().execute("UPDATE mra_usage SET status='uncertain' WHERE id=$1 AND owner_id=$2 AND run_id=$3 AND status='reserved'",db.uid(reservation),db.uid(scope.owner_id),db.uid(scope.run_id))
