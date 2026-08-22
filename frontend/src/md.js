import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ breaks: true })

export function renderMd(text) {
  return { __html: DOMPurify.sanitize(marked.parse(text || '')) }
}
