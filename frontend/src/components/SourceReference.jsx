import { FileText } from 'lucide-react'

/** A clickable citation chip, e.g. "[S1] report.pdf · page 5". Opens the PDF at that page. */
export default function SourceReference({ source, onOpen }) {
  return (
    <button
      type="button"
      onClick={() => onOpen && onOpen(source)}
      title={source.relevant_text}
      className="group inline-flex max-w-full items-center gap-2 rounded-xl border border-indigo-100 bg-indigo-50/70 px-3 py-1.5 text-left text-xs font-medium text-indigo-700 transition hover:border-indigo-300 hover:bg-indigo-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400"
    >
      <FileText size={14} aria-hidden="true" className="shrink-0" />
      <span className="truncate">
        <span className="font-semibold">[{source.source_id}]</span> {source.filename} · page {source.page_number}
      </span>
    </button>
  )
}
