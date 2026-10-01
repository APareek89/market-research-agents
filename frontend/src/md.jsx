import React, { useEffect, useRef, useState } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ breaks: true, gfm: true })

export function renderMd(text) {
  return { __html: DOMPurify.sanitize(marked.parse(text || '')) }
}

let mermaidP = null
function loadMermaid() {
  if (!mermaidP) mermaidP = import('mermaid').then(({ default: mermaid }) => mermaid)
  return mermaidP
}
let diagramQueue = Promise.resolve()
function renderDiagram(id, source, theme) {
  const result = diagramQueue.then(async () => {
    const mermaid = await loadMermaid()
    mermaid.initialize({ startOnLoad: false, theme, securityLevel: 'strict', flowchart: { htmlLabels: false } })
    return mermaid.render(id, source)
  })
  diagramQueue = result.catch(() => {})
  return result
}

let mid = 0

/** Markdown block that also renders ```mermaid fences as live diagrams. */
export function MdContent({ text }) {
  const ref = useRef(null)
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'neutral')
  useEffect(() => {
    const change = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'neutral')
    window.addEventListener('mra-theme-change', change)
    return () => window.removeEventListener('mra-theme-change', change)
  }, [])
  useEffect(() => {
    if (ref.current) ref.current.innerHTML = renderMd(text).__html
    const codes = ref.current?.querySelectorAll('code.language-mermaid')
    if (!codes?.length) return
    let cancelled = false
    ;(async () => {
      for (const code of [...codes]) {
        try {
          const { svg } = await renderDiagram(`mmd${++mid}`, code.textContent, theme)
          if (cancelled) return
          const holder = document.createElement('div')
          holder.className = 'mermaid-holder'
          holder.innerHTML = svg
          code.closest('pre')?.replaceWith(holder)
        } catch {
          /* leave the fence as code if the diagram doesn't parse */
        }
      }
    })()
    return () => { cancelled = true }
  }, [text, theme])
  return <div ref={ref} className="md" dangerouslySetInnerHTML={renderMd(text)} />
}

function svgToPng(svg) {
  return new Promise((resolve) => {
    const div = document.createElement('div')
    div.innerHTML = svg
    const el = div.querySelector('svg')
    if (!el) return resolve(null)
    let w = 1200, h = 700
    const vb = (el.getAttribute('viewBox') || '').split(/[\s,]+/).map(Number)
    if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) { w = vb[2]; h = vb[3] }
    const scale = Math.min(1600 / w, 4)
    el.setAttribute('width', Math.round(w * scale))
    el.setAttribute('height', Math.round(h * scale))
    // XMLSerializer keeps foreignObject label content well-formed XML;
    // innerHTML serialization produces HTML that breaks SVG-as-image loading.
    const xml = new XMLSerializer().serializeToString(el)
    const img = new Image()
    img.onload = () => {
      try {
        const c = document.createElement('canvas')
        c.width = Math.round(w * scale)
        c.height = Math.round(h * scale)
        const ctx = c.getContext('2d')
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, c.width, c.height)
        ctx.drawImage(img, 0, 0, c.width, c.height)
        resolve(c.toDataURL('image/png'))
      } catch {
        resolve(null)
      }
    }
    img.onerror = () => resolve(null)
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml)
  })
}

/** Rasterize every ```mermaid block in the markdown to PNG data URLs (in order),
 * re-rendered on a LIGHT theme so they read well on white documents/slides. */
export async function renderMermaidPngs(markdown) {
  const blocks = [...(markdown || '').matchAll(/```mermaid\s*\n([\s\S]*?)```/g)].map((m) => m[1])
  if (!blocks.length) return []
  const pngs = []
  for (const block of blocks) {
    try {
      const { svg } = await renderDiagram(`exp${++mid}`, block, 'neutral')
      pngs.push(await svgToPng(svg))
    } catch {
      pngs.push(null)
    }
  }
  return pngs
}
