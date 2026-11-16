import { ExternalLink, FileText } from 'lucide-react'
import { api } from '../../services/api'

/**
 * A source for an answer: file name, page, the excerpt the answer used, and two actions.
 * "Open at page" shows the PDF beside the chat. "Open document" opens the whole PDF in a new tab.
 */
export default function CitationCard({ source, onOpenPage }) {
  const openDocumentUrl = `${api.documentFileUrl(source.document_id)}#page=${source.page_number}`
  return (
    <article className="citation-card" data-testid="citation-card">
      <div className="flex min-w-0 items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
          <FileText size={14} aria-hidden="true" />
        </span>
        <p className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900" title={source.filename}>
          {source.filename}
        </p>
        <span className="shrink-0 rounded-full bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-700">
          Page {source.page_number}
        </span>
      </div>
      {source.relevant_text && <p className="citation-excerpt">{source.relevant_text}</p>}
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onOpenPage && onOpenPage(source)}
          className="rounded-lg bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-indigo-700"
        >
          Open at page {source.page_number}
        </button>
        <a
          href={openDocumentUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
        >
          <ExternalLink size={12} aria-hidden="true" /> Open document
        </a>
      </div>
    </article>
  )
}
