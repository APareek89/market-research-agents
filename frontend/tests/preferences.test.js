import test from 'node:test'
import assert from 'node:assert/strict'
import {loadPreference,readPreference,writePreference,removePreference} from '../src/preferences.js'
test('valid JSON with invalid preference shapes is discarded before React receives it',()=>{
  for(const [kind,bad] of [['custom_agents',{}],['custom_agents',[{id:'x',name:{},system_prompt:'x'}]],['stage_order','abc'],['toggles',{reviewer:'false',client:true,custom:{}}],['agents',{intake:{name:[],system_prompt:'x'}}]]) {
    global.localStorage={getItem:()=>JSON.stringify(bad)}
    assert.equal(loadPreference('test',kind,null),null)
  }
})
test('valid per-owner preferences survive; stored keys and unknown settings do not',()=>{
  global.localStorage={getItem:()=>JSON.stringify({provider:'openai',model:'gpt-5-mini',api_key:'not-a-real-key',extra:true})}
  assert.deepEqual(loadPreference('owner:settings','settings',{}),{provider:'openai',model:'gpt-5-mini'})
  const custom=[{id:'tone',name:'Tone',system_prompt:'Keep concise',mode:'transformer'}]
  global.localStorage={getItem:()=>JSON.stringify(custom)}
  assert.deepEqual(loadPreference('owner:custom','custom_agents',[]),custom)
})
test('blocked storage is optional for reads writes removal and defaults',()=>{
  global.localStorage={getItem(){throw Error('blocked')},setItem(){throw Error('quota')},removeItem(){throw Error('blocked')}}
  assert.equal(readPreference('key'),null);writePreference('key','text');removePreference('key')
  assert.deepEqual(loadPreference('key','custom_agents',[]),[])
})
