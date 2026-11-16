import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, ExternalLink, Minus, Plus, X } from 'lucide-react'
import { api } from '../services/api'

export const ZOOM_LEVELS = [50, 75, 100, 125, 150, 200]

/**
 * Shows a stored PDF with the browser's built-in viewer.
 * The page and zoom are passed in the URL (#page=5&zoom=125), which all major
 * browsers understand. The buttons below change those values.
 */
export default function PDFViewer({ documentId, filename, page = 1, pageCount = null, onClose }) {
  const [currentPage, setCurrentPage] = useState(page)
  const [zoomIndex, setZoomIndex] = useState(ZOOM_LEVELS.indexOf(100))

  useEffect(() => {
    setCurrentPage(page)
  }, [page, documentId])

  const zoom = ZOOM_LEVELS[zoomIndex]
  const fileUrl = api.documentFileUrl(documentId)
  const src = `${fileUrl}#page=${currentPage}&zoom=${zoom}`
  const lastPage = pageCount || null

  const goToPage = (next) => {
    const bounded = Math.max(1, lastPage ? Math.min(next, lastPage) : next)
    setCurrentPage(bounded)
  }

  return (
    <aside
      aria-label="PDF viewer"
      className="animate-fade-up flex h-full min-h-0 w-full flex-col border-l border-slate-200 bg-white"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-900" title={filename}>
            {filename}
          </p>
          <p className="text-xs text-slate-500">
            Page {currentPage}
            {lastPage ? ` of ${lastPage}` : ''} · {zoom}%
          </p>
        </div>

        <div className="flex items-center gap-1" role="group" aria-label="Page navigation">
          <button
            type="button"
            aria-label="Previous page"
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
          >
            <ChevronLeft size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Next page"
            onClick={() => goToPage(currentPage + 1)}
            disabled={lastPage !== null && currentPage >= lastPage}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
          >
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="flex items-center gap-1" role="group" aria-label="Zoom">
          <button
            type="button"
            aria-label="Zoom out"
            onClick={() => setZoomIndex((index) => Math.max(0, index - 1))}
            disabled={zoomIndex === 0}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
          >
            <Minus size={18} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            onClick={() => setZoomIndex((index) => Math.min(ZOOM_LEVELS.length - 1, index + 1))}
            disabled={zoomIndex === ZOOM_LEVELS.length - 1}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 disabled:opacity-40"
          >
            <Plus size={18} aria-hidden="true" />
          </button>
        </div>

        <a
          href={fileUrl}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
          aria-label="Open PDF in a new tab"
          title="Open in new tab"
        >
          <ExternalLink size={18} aria-hidden="true" />
        </a>

        {onClose && (
          <button
            type="button"
            aria-label="Close PDF viewer"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"
          >
            <X size={18} aria-hidden="true" />
          </button>
        )}
      </header>

      <iframe
        key={documentId}
        title={`PDF: ${filename}`}
        src={src}
        className="min-h-0 w-full flex-1 bg-slate-100"
      />
    </aside>
  )
}
