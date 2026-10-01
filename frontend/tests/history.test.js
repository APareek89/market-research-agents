import test from 'node:test'
import assert from 'node:assert/strict'
import { savedConversationRuns, restoreConversationRuns } from '../src/history.js'

const fixture = [
  { id: 'q1', role: 'user', content: 'Pricing question' },
  { id: 'a1', role: 'assistant', content: 'Prepared report', created_at: '2026-09-30T10:00:00Z', trace: { steps: [
    { node: 'user', output: 'Original question' },
    { node: 'intake', agent: 'Scout', model: 'Prepared example — no provider', cached: true, output: 'Original brief', elapsed: .1 },
    { node: 'analyst', agent: 'Astra', model: 'Prepared example — no provider', cached: true, output: 'Original report', elapsed: .2 },
  ] } },
]

test('saved history restores exact cached steps, initiating input and stable identity', () => {
  const [run] = savedConversationRuns('conversation-a', fixture)
  assert.equal(run.id, 'saved:conversation-a:a1')
  assert.equal(run.input, 'Original question')
  assert.equal(run.status, 'saved')
  assert.equal(run.cached, true)
  assert.deepEqual(run.steps, fixture[1].trace.steps.slice(1))
  assert.equal(run.at, new Date(fixture[1].created_at).toLocaleString())
  assert.equal(run.total, undefined, 'do not invent wall-clock runtime from node timings')
})

test('loading history again is idempotent and preserves active/error/other conversations', () => {
  const existing = [
    { id: 'live-old', conversationId: 'conversation-a', status: 'done' },
    { id: 'live-active', conversationId: 'conversation-a', status: 'running' },
    { id: 'live-error', conversationId: 'conversation-a', status: 'error' },
    { id: 'other', conversationId: 'conversation-b', status: 'done' },
  ]
  const once = restoreConversationRuns(existing, 'conversation-a', fixture)
  const twice = restoreConversationRuns(once, 'conversation-a', fixture)
  assert.deepEqual(twice, once)
  assert.deepEqual(once.map(run => run.id), ['saved:conversation-a:a1', 'live-active', 'live-error', 'other'])
})

test('partial and older traces stay honest; absent traces do not invent runs', () => {
  const messages = [...fixture,
    { role: 'user', content: 'Next question' },
    { id: 'a2', role: 'assistant', content: 'Stopped', trace: { steps: [{ node: 'intake', output: 'Partial brief' }] } },
    { id: 'a3', role: 'assistant', content: 'No stored trace' },
  ]
  const runs = savedConversationRuns('conversation-a', messages)
  assert.equal(runs.length, 2)
  assert.equal(runs[0].status, 'saved')
  assert.equal(runs[0].cached, false)
  assert.equal(runs[0].input, 'Next question')
  assert.equal(runs[0].at, 'Saved conversation')
})
