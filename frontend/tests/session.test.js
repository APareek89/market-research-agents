import test from 'node:test'
import assert from 'node:assert/strict'
import { acceptSession, request, captureSession, assertCurrentSession, createSessionFence } from '../src/session.js'

test('mutation sends current CSRF token and preserves multipart boundary ownership', async () => {
  acceptSession({ enabled: true, user: { id: 'owner-a' }, csrf_token: 'fixture-csrf-a' })
  const previous = globalThis.fetch
  const form = new FormData(); form.set('message', 'synthetic question')
  globalThis.fetch = async (path, options) => {
    assert.equal(path, '/api/chat')
    assert.equal(options.headers.get('X-CSRF-Token'), 'fixture-csrf-a')
    assert.equal(options.headers.has('Content-Type'), false)
    assert.equal(options.body, form)
    return new Response('{}', { status: 200 })
  }
  try { await request('/api/chat', { method: 'POST', body: form }) } finally { globalThis.fetch = previous }
})

test('delayed A401 cannot sign out the newer owner B', async () => {
  const previous = globalThis.fetch, previousWindow = globalThis.window
  let expired = 0, finish
  globalThis.window = { dispatchEvent: () => expired++ }
  globalThis.fetch = () => new Promise(resolve => { finish = resolve })
  acceptSession({ enabled: true, user: { id: 'a' }, csrf_token: 'fixture-a' })
  const response = request('/api/conversations')
  acceptSession({ enabled: true, user: null, csrf_token: 'fixture-anon' })
  acceptSession({ enabled: true, user: { id: 'b' }, csrf_token: 'fixture-b' })
  finish(new Response('{}', { status: 401 }))
  try { await assert.rejects(response, error => error.name === 'AbortError'); assert.equal(expired, 0) }
  finally { globalThis.fetch = previous; globalThis.window = previousWindow }
})

test('current-session401 still expires after a same-owner refresh', async () => {
  const previous = globalThis.fetch, previousWindow = globalThis.window
  let expired = 0
  globalThis.window = { dispatchEvent: () => expired++ }
  globalThis.fetch = async () => new Response('{"detail":"Sign in again"}', { status: 401 })
  acceptSession({ enabled: true, user: { id: 'b' }, csrf_token: 'fixture-b' })
  const current = captureSession()
  acceptSession({ enabled: true, user: { id: 'b' }, csrf_token: 'fixture-b-refresh' })
  assertCurrentSession(current)
  try { await assert.rejects(request('/api/conversations'), /Sign in again/); assert.equal(expired, 1); assert.throws(() => assertCurrentSession(current), { name: 'AbortError' }) }
  finally { globalThis.fetch = previous; globalThis.window = previousWindow }
})

test('returning to the same owner never revives an old request', () => {
  const fence = createSessionFence()
  fence.accept('a'); const old = fence.capture()
  fence.accept(null); fence.accept('a')
  assert.equal(fence.current(old), false)
})

test('auth input error is readable without expiring the current anonymous CSRF context', async () => {
  const previous = globalThis.fetch, previousWindow = globalThis.window
  globalThis.window = { dispatchEvent: () => assert.fail('auth form error must not reset gate') }
  globalThis.fetch = async () => new Response('{"detail":"Email or password is incorrect"}', { status: 401 })
  acceptSession({ enabled: true, user: null, csrf_token: 'fixture-anon' })
  try { await assert.rejects(request('/api/auth/signin', { method: 'POST', body: '{}' }), /Email or password/); assertCurrentSession(captureSession()) }
  finally { globalThis.fetch = previous; globalThis.window = previousWindow }
})

test('a delayed SSE frame is discarded and the viewer closes after account switch', async () => {
  const { attachRun } = await import('../src/api.js')
  const previous = globalThis.fetch
  let controller, canceled = false
  const body = new ReadableStream({ start(value) { controller = value }, cancel() { canceled = true } })
  globalThis.fetch = async () => new Response(body, { status: 200 })
  acceptSession({ enabled: true, user: { id: 'stream-a' }, csrf_token: 'fixture-a' })
  const stream = attachRun('fixture-conversation', () => assert.fail('old frame reached the new session'))
  await new Promise(resolve => setImmediate(resolve))
  acceptSession({ enabled: true, user: { id: 'stream-b' }, csrf_token: 'fixture-b' })
  controller.enqueue(new TextEncoder().encode('data: {"type":"final","output":"old owner"}\n\n'))
  try { await assert.rejects(stream, { name: 'AbortError' }); assert.equal(canceled, true) }
  finally { globalThis.fetch = previous }
})

test('an export body finishing after account switch cannot trigger a download', async () => {
  const { exportReport } = await import('../src/api.js')
  const previous = globalThis.fetch
  let finish
  globalThis.fetch = async () => ({ ok: true, blob: () => new Promise(resolve => { finish = resolve }) })
  acceptSession({ enabled: true, user: { id: 'export-a' }, csrf_token: 'fixture-a' })
  const download = exportReport('pdf', 'Fixture', 'Synthetic report')
  await new Promise(resolve => setImmediate(resolve))
  acceptSession({ enabled: true, user: { id: 'export-b' }, csrf_token: 'fixture-b' })
  finish(new Blob(['fixture']))
  try { await assert.rejects(download, { name: 'AbortError' }) }
  finally { globalThis.fetch = previous }
})

test('a JSON body parsed after account switch is rejected', async () => {
  const { getConversations } = await import('../src/api.js')
  const previous = globalThis.fetch
  let finish
  globalThis.fetch = async () => ({ ok: true, json: () => new Promise(resolve => { finish = resolve }) })
  acceptSession({ enabled: true, user: { id: 'json-a' }, csrf_token: 'fixture-a' })
  const pending = getConversations()
  await new Promise(resolve => setImmediate(resolve))
  acceptSession({ enabled: true, user: { id: 'json-b' }, csrf_token: 'fixture-b' })
  finish([{ id: 'owner-a-conversation' }])
  try { await assert.rejects(pending, { name: 'AbortError' }) }
  finally { globalThis.fetch = previous }
})

test('explicit local fixture mode supports mutations without fabricating a CSRF token', async () => {
  const previous = globalThis.fetch
  acceptSession({ enabled: false, user: { id: 'fixture' }, csrf_token: '' })
  globalThis.fetch = async (path, options) => {
    assert.equal(options.headers.has('X-CSRF-Token'), false)
    return new Response('{}')
  }
  try { await request('/api/examples/market-entry', { method: 'POST', body: '{}' }) }
  finally { globalThis.fetch = previous; acceptSession({ enabled: true, user: null }) }
})

test('SSE expiry closes the current session only and never delivers following private frames', async () => {
  const { attachRun } = await import('../src/api.js')
  const previous = globalThis.fetch, previousWindow = globalThis.window
  try {
    for (const stale of [false, true]) {
      let controller, canceled = false, expired = 0
      globalThis.window = { dispatchEvent: () => expired++ }
      globalThis.fetch = async () => new Response(new ReadableStream({
        start(value) { controller = value }, cancel() { canceled = true },
      }))
      acceptSession({ enabled: true, user: { id: 'expiry-a' }, csrf_token: 'fixture-a' })
      const stream = attachRun('expiry-conversation', () => assert.fail('expired stream delivered a private frame'))
      await new Promise(resolve => setImmediate(resolve))
      if (stale) acceptSession({ enabled: true, user: { id: 'expiry-b' }, csrf_token: 'fixture-b' })
      const current = captureSession()
      controller.enqueue(new TextEncoder().encode('data: {"type":"session_expired"}\n\ndata: {"type":"final","output":"private"}\n\n'))
      await assert.rejects(stream, { name: 'AbortError' })
      assert.equal(expired, stale ? 0 : 1)
      assert.equal(canceled, true)
      if (stale) assertCurrentSession(current)
      else assert.throws(() => assertCurrentSession(current), { name: 'AbortError' })
    }
  } finally { globalThis.fetch = previous; globalThis.window = previousWindow }
})
