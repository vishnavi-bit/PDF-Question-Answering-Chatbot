import { useState } from 'react'
import { AlertTriangle, BookOpen, CheckCircle2, FileText, Loader2, MessageSquare, Trash2 } from 'lucide-react'
import { api, getErrorMessage } from '../services/api'
import { AnswerText } from '../utils/formatAnswer'

const STATUS_STYLES = {
  ready: { label: 'Ready', className: 'bg-emerald-50 text-emerald-700 ring-emerald-200', Icon: CheckCircle2 },
  processing: { label: 'Processing', className: 'bg-amber-50 text-amber-700 ring-amber-200', Icon: Loader2 },
  needs_ocr: { label: 'OCR needed', className: 'bg-orange-50 text-orange-700 ring-orange-200', Icon: AlertTriangle },
  password_protected: { label: 'Password protected', className: 'bg-rose-50 text-rose-700 ring-rose-200', Icon: AlertTriangle },
  too_large: { label: 'Too many pages', className: 'bg-orange-50 text-orange-700 ring-orange-200', Icon: AlertTriangle },
  empty: { label: 'No text', className: 'bg-slate-100 text-slate-600 ring-slate-200', Icon: AlertTriangle },
  corrupt: { label: 'Unreadable', className: 'bg-rose-50 text-rose-700 ring-rose-200', Icon: AlertTriangle },
  failed: { label: 'Failed', className: 'bg-rose-50 text-rose-700 ring-rose-200', Icon: AlertTriangle },
}

export function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || STATUS_STYLES.failed
  const { Icon } = style
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${style.className}`}>
      <Icon size={12} aria-hidden="true" className={status === 'processing' ? 'animate-spin' : ''} />
      {style.label}
    </span>
  )
}

function formatSize(bytes) {
  if (!bytes) return '0 KB'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** One uploaded document: status, selection, delete, ask, and an inline summary. */
export default function DocumentCard({ document, selected = false, onToggleSelect, onDelete, onAsk }) {
  const [summaryMode, setSummaryMode] = useState(null)
  const [summary, setSummary] = useState(null)
  const [summaryError, setSummaryError] = useState('')
  const [summaryLoading, setSummaryLoading] = useState(false)
  const isReady = document.processing_status === 'ready'

  const loadSummary = async (mode) => {
    setSummaryMode(mode)
    setSummary(null)
    setSummaryError('')
    setSummaryLoading(true)
    try {
      setSummary(await api.summarizeDocument(document.id, mode))
    } catch (err) {
      setSummaryError(getErrorMessage(err, 'The summary could not be created.'))
    } finally {
      setSummaryLoading(false)
    }
  }

  return (
    <article className="animate-fade-up flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md" data-testid="document-card">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
          <FileText size={20} aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold text-slate-900" title={document.filename}>
            {document.filename}
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {isReady ? `${document.page_count} pages · ${document.total_chunks} chunks · ` : ''}
            {formatSize(document.file_size)}
          </p>
          {isReady && (document.table_count > 0 || document.pages_without_text > 0) && (
            <p className="mt-0.5 text-xs text-slate-500" data-testid="extraction-details">
              {document.table_count > 0 && `${document.table_count} table${document.table_count === 1 ? '' : 's'} indexed`}
              {document.table_count > 0 && document.pages_without_text > 0 && ' · '}
              {document.pages_without_text > 0 &&
                `${document.pages_without_text} page${document.pages_without_text === 1 ? '' : 's'} with no text (may be scanned images)`}
            </p>
          )}
        </div>
        <StatusBadge status={document.processing_status} />
      </div>

      {document.error_message && (
        <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{document.error_message}</p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {onToggleSelect && isReady && (
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
            <input
              type="checkbox"
              checked={selected}
              onChange={() => onToggleSelect(document.id)}
              className="h-4 w-4 accent-indigo-600"
            />
            Use in chat
          </label>
        )}
        {onAsk && isReady && (
          <button
            type="button"
            onClick={() => onAsk(document.id)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
          >
            <MessageSquare size={14} aria-hidden="true" /> Ask this document
          </button>
        )}
        {isReady && (
          <>
            <button
              type="button"
              onClick={() => loadSummary('overview')}
              disabled={summaryLoading}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            >
              <BookOpen size={14} aria-hidden="true" /> Summary
            </button>
            <button
              type="button"
              onClick={() => loadSummary('chapters')}
              disabled={summaryLoading}
              className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            >
              Chapter summaries
            </button>
          </>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(document)}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-rose-600 hover:bg-rose-50"
          >
            <Trash2 size={14} aria-hidden="true" /> Delete
          </button>
        )}
      </div>

      {summaryMode && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/70 p-4" aria-live="polite">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {summaryMode === 'chapters' ? 'Chapter summaries' : 'Document summary'}
          </p>
          {summaryLoading && <p className="text-sm text-slate-500">Writing the summary…</p>}
          {summaryError && <p className="text-sm text-rose-600">{summaryError}</p>}
          {summary && summary.mode === 'overview' && summary.summary && <AnswerText text={summary.summary} />}
          {summary && summary.mode === 'chapters' && summary.chapters.length > 0 && (
            <div className="space-y-4">
              {summary.chapters.map((chapter) => (
                <section key={`${chapter.title}-${chapter.page_start}`}>
                  <h4 className="text-sm font-semibold text-slate-900">
                    {chapter.title} <span className="font-normal text-slate-500">(page {chapter.page_start})</span>
                  </h4>
                  <AnswerText text={chapter.summary} />
                </section>
              ))}
            </div>
          )}
          {summary && summary.note && <p className="mt-3 text-xs text-slate-500">{summary.note}</p>}
        </div>
      )}
    </article>
  )
}
