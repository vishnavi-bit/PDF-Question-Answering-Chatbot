import { useState } from 'react'
import { api, getErrorMessage } from '../../services/api'
import ExportButton from './ExportButton'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

const LENGTHS = [
  { value: 'short', label: 'Short' },
  { value: 'detailed', label: 'Detailed' },
]

/** Study notes: choose Short or Detailed, generate, edit, save and download as PDF. */
export default function NotesPanel({ documentIds }) {
  const [length, setLength] = useState('detailed')
  const [note, setNote] = useState(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [overviewDraft, setOverviewDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const showNote = (saved) => {
    setNote(saved)
    setTitleDraft(saved.title)
    setOverviewDraft(saved.body.overview || '')
  }

  const generate = async () => {
    setLoading(true)
    setError('')
    setNotice('')
    try {
      showNote(await api.saveNotes({ mode: 'overview', length, document_ids: documentIds }))
      setNotice('Notes created and saved.')
    } catch (err) {
      setNote(null)
      setError(getErrorMessage(err, 'The notes could not be created.'))
    } finally {
      setLoading(false)
    }
  }

  const save = async () => {
    setError('')
    setNotice('')
    try {
      const updated = await api.updateSavedNotes(note.id, {
        title: titleDraft.trim() || note.title,
        body: { ...note.body, overview: overviewDraft.trim() || null },
      })
      showNote(updated)
      setNotice('Changes saved.')
    } catch (err) {
      setError(getErrorMessage(err, 'The changes could not be saved.'))
    }
  }

  const body = note ? note.body : null

  return (
    <section aria-labelledby="notes-heading" className="space-y-5">
      <div>
        <h2 id="notes-heading" className="text-lg font-semibold text-slate-900">Study notes</h2>
        <p className="text-sm text-slate-500">Make short notes from your PDF. Every point shows its page.</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Notes length" className="inline-flex rounded-xl border border-slate-200 bg-white p-1">
          {LENGTHS.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={length === item.value}
              onClick={() => setLength(item.value)}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${length === item.value ? 'bg-indigo-600 text-white' : 'text-slate-600'}`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={loading}
          className="brand-gradient rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-200 disabled:opacity-50"
        >
          Generate Notes
        </button>
      </div>

      {loading && <StudyLoading label="Writing your notes…" />}
      <StudyError message={error} />
      {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}

      {note && body && (
        <div className="space-y-5" data-testid="notes-result">
          <div className="flex flex-wrap items-end gap-2">
            <label className="min-w-0 flex-1 text-sm text-slate-600">
              Title
              <input
                aria-label="Notes title"
                value={titleDraft}
                maxLength={200}
                onChange={(event) => setTitleDraft(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <ExportButton kind="notes" itemId={note.id} label="Download PDF" />
          </div>

          <label className="block text-sm text-slate-600">
            Overview
            <textarea
              aria-label="Overview"
              rows={5}
              value={overviewDraft}
              onChange={(event) => setOverviewDraft(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-6"
            />
          </label>
          <button type="button" onClick={save} className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">
            Save changes
          </button>

          {body.key_points.length > 0 && (
            <div>
              <h3 className="mb-2 font-semibold text-slate-900">Important points</h3>
              <ul className="space-y-3 text-sm text-slate-700">
                {body.key_points.map((point, index) => (
                  <li key={index}>• {point.text}<StudyCitations sources={point.sources} /></li>
                ))}
              </ul>
            </div>
          )}

          {body.definitions.length > 0 && (
            <div>
              <h3 className="mb-2 font-semibold text-slate-900">Words to know</h3>
              <dl className="space-y-3 text-sm">
                {body.definitions.map((item, index) => (
                  <div key={index}>
                    <dt className="font-semibold text-indigo-700">{item.term}</dt>
                    <dd className="text-slate-700">{item.meaning}</dd>
                    <StudyCitations sources={item.sources} />
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
