import { useState } from 'react'
import { Download, Loader2 } from 'lucide-react'
import { api, getErrorMessage } from '../../services/api'

/** Save a blob to the user's computer through a temporary link. */
export function saveBlob(blob, fileName) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Downloads a PDF export of a saved study item. Shows a message if it fails. */
export default function ExportButton({ kind, itemId, label = 'Download PDF', fileName }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const download = async () => {
    setBusy(true)
    setError('')
    try {
      const blob = await api.exportPdf(kind, itemId)
      saveBlob(blob, fileName || (itemId === undefined ? `${kind}.pdf` : `${kind}-${itemId}.pdf`))
    } catch (err) {
      setError(getErrorMessage(err, 'The PDF could not be created.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={download}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50"
      >
        {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <Download size={16} aria-hidden="true" />}
        {label}
      </button>
      {error && <span role="alert" className="text-xs text-rose-600">{error}</span>}
    </span>
  )
}
