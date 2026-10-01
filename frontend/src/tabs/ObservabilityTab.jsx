import React, { useState } from 'react'
import { MdContent } from '../md.jsx'

export default function ObservabilityTab({ runs }) {
  const [openStep, setOpenStep] = useState(null) // `${runId}:${idx}`

  if (!runs.length) {
    return (
      <div className="empty tall">
        <h2>No trace selected yet.</h2>
        <p>Open a saved conversation or run a prepared example in Chat. Each recorded agent step appears here with its output and timing.</p>
      </div>
    )
  }

  return (
    <div className="obs-layout">
      {runs.map((run) => (
        <div key={run.id} className="run-card">
          <div className="run-head">
            <span className={`status ${run.status}`}>{run.status}</span>
            {run.cached && <span className="example-badge">Prepared · no provider</span>}
            <span className="run-input">{run.input?.slice(0, 120)}</span>
            <span className="run-meta">{run.at}{run.total ? ` · ${run.total}s total` : ''}</span>
          </div>
          {run.error && <div className="error-box">⚠ {run.error}</div>}
          <div className="flow">
            {(run.steps || []).map((s, i) => {
              const key = `${run.id}:${i}`
              const open = openStep === key
              return (
                <div key={key} className="flow-step">
                  <button className="flow-node" aria-expanded={open} onClick={() => setOpenStep(open ? null : key)}>
                    <span className="flow-agent">{s.agent}</span>
                    <span className="flow-label">{s.label}</span>
                    <span className="flow-time">{s.elapsed}s{s.model ? ` · ${s.model.replace('claude-', '')}` : ''}</span>
                    <span className="flow-caret">{open ? '▾' : '▸'}</span>
                  </button>
                  {open && <div className="flow-output"><MdContent text={s.output} /></div>}
                  {i < run.steps.length - 1 && <div className="flow-arrow">↓</div>}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
