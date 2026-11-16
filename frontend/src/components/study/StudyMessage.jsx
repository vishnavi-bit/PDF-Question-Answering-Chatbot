import { AlertCircle, Loader2 } from 'lucide-react'

/** Shared loading and error messages for the study panels. */
export function StudyLoading({ label = 'Creating study material from your PDFs…' }) {
  return (
    <div role="status" className="flex items-center gap-2 rounded-xl bg-indigo-50 px-4 py-3 text-sm text-indigo-700">
      <Loader2 size={16} className="animate-spin" aria-hidden="true" /> {label}
    </div>
  )
}

export function StudyError({ message }) {
  if (!message) return null
  return (
    <div role="alert" className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> <span>{message}</span>
    </div>
  )
}

/** Human-readable description of which PDFs will be studied. */
export function scopeLabel(documentIds, documents) {
  const ready = documents.filter((doc) => doc.processing_status === 'ready')
  if (!documentIds.length) return `All ${ready.length} ready PDF${ready.length === 1 ? '' : 's'}`
  return `${documentIds.length} selected PDF${documentIds.length === 1 ? '' : 's'}`
}
