import { useCallback, useEffect, useState } from 'react'
import { api, getErrorMessage } from '../../services/api'
import ExportButton from './ExportButton'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

const MODES = [
  ['overview', 'Overview'],
  ['chapter', 'Chapter-wise'],
  ['topic', 'Topic'],
]

/** Saved notes: create and keep notes, reopen them, edit the overview and title, export or delete them. */
export default function SavedNotes({ documentIds }) {
  const [list, setList] = useState([])
  const [mode, setMode] = useState('overview')
  const [length, setLength] = useState('detailed')
  const [topic, setTopic] = useState('')
  const [openNote, setOpenNote] = useState(null)
  const [overviewDraft, setOverviewDraft] = useState('')
  const [titleDraft, setTitleDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const refresh = useCallback(async () => {
    try {
      const data = await api.listSavedNotes()
      setList(data.notes)
    } catch (err) {
      setError(getErrorMessage(err, 'Saved notes could not be loaded.'))
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const create = async (event) => {
    event.preventDefault()
    if (mode === 'topic' && topic.trim().length < 2) {
      setError('Enter a topic of at least two characters.')
      return
    }
    setLoading(true)
    setError('')
    setNotice('')
    try {
      const note = await api.saveNotes({
        mode,
        length,
        document_ids: documentIds,
        ...(mode === 'topic' ? { topic: topic.trim() } : {}),
      })
      setNotice('Notes saved.')
      setOpenNote(note)
      setOverviewDraft(note.body.overview || '')
      setTitleDraft(note.title)
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The notes could not be saved.'))
    } finally {
      setLoading(false)
    }
  }

  const open = async (id) => {
    setError('')
    setNotice('')
    try {
      const note = await api.getSavedNotes(id)
      setOpenNote(note)
      setOverviewDraft(note.body.overview || '')
      setTitleDraft(note.title)
    } catch (err) {
      setError(getErrorMessage(err, 'These notes could not be opened.'))
    }
  }

  const saveChanges = async () => {
    setError('')
    setNotice('')
    try {
      const updated = await api.updateSavedNotes(openNote.id, {
        title: titleDraft.trim() || openNote.title,
        body: { ...openNote.body, overview: overviewDraft.trim() || null },
      })
      setOpenNote(updated)
      setNotice('Changes saved.')
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The changes could not be saved.'))
    }
  }

  const remove = async (id) => {
    if (!window.confirm('Delete these saved notes? This cannot be undone.')) return
    try {
      await api.deleteSavedNotes(id)
      if (openNote && openNote.id === id) setOpenNote(null)
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The notes could not be deleted.'))
    }
  }

  const body = openNote ? openNote.body : null

  return (
    <section aria-labelledby="saved-notes-heading" className="space-y-4 border-t border-slate-200 pt-6">
      <div>
        <h3 id="saved-notes-heading" className="text-base font-semibold text-slate-900">Saved notes</h3>
        <p className="text-sm text-slate-500">Create notes once, keep them, edit the overview and download them as PDF.</p>
      </div>

      <form onSubmit={create} className="flex flex-wrap items-end gap-2" aria-label="Create saved notes">
        <label className="text-sm text-slate-600">
          Type
          <select aria-label="Saved notes type" value={mode} onChange={(e) => setMode(e.target.value)}
            className="ml-2 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm">
            {MODES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          Length
          <select aria-label="Saved notes length" value={length} onChange={(e) => setLength(e.target.value)}
            className="ml-2 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm">
            <option value="short">Short</option>
            <option value="detailed">Detailed</option>
          </select>
        </label>
        {mode === 'topic' && (
          <label className="text-sm text-slate-600">
            Topic
            <input aria-label="Notes topic" value={topic} maxLength={200} onChange={(e) => setTopic(e.target.value)}
              className="ml-2 w-56 rounded-lg border border-slate-300 px-2 py-2 text-sm" />
          </label>
        )}
        <button type="submit" disabled={loading}
          className="brand-gradient rounded-xl px-4 py-2 text-sm font-semibold text-white shadow-md shadow-indigo-200 disabled:opacity-50">
          Create and save
        </button>
      </form>

      {loading && <StudyLoading label="Creating and saving notes from your PDFs…" />}
      <StudyError message={error} />
      {notice && <p role="status" className="text-sm text-emerald-700">{notice}</p>}

      {list.length === 0 ? (
        <p className="text-sm text-slate-500">No saved notes yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-2xl border border-slate-200" aria-label="Saved notes list">
          {list.map((note) => (
            <li key={note.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <span className="text-sm font-medium text-slate-800">{note.title}</span>
              <span className="flex gap-2">
                <button type="button" onClick={() => open(note.id)}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700">Open</button>
                <button type="button" onClick={() => remove(note.id)}
                  className="rounded-lg border border-rose-300 px-3 py-1.5 text-sm text-rose-700">Delete</button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {openNote && body && (
        <article className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="saved-note-view">
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex-1 text-sm text-slate-600">
              Title
              <input aria-label="Saved notes title" value={titleDraft} maxLength={200}
                onChange={(e) => setTitleDraft(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
            <ExportButton kind="notes" itemId={openNote.id} label="Download PDF" />
          </div>

          <label className="block text-sm text-slate-600">
            Overview (you can edit this)
            <textarea aria-label="Notes overview" value={overviewDraft} rows={4} onChange={(e) => setOverviewDraft(e.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-6" />
          </label>
          <div className="flex gap-2">
            <button type="button" onClick={saveChanges}
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Save changes</button>
          </div>

          {body.key_points.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-900">Important points</h4>
              <ul className="space-y-2 text-sm text-slate-700">
                {body.key_points.map((point, index) => (
                  <li key={index}>• {point.text}<StudyCitations sources={point.sources} /></li>
                ))}
              </ul>
            </div>
          )}
          {body.definitions.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-900">Definitions</h4>
              <dl className="space-y-2 text-sm">
                {body.definitions.map((item, index) => (
                  <div key={index}><dt className="font-semibold text-indigo-700">{item.term}</dt>
                    <dd className="text-slate-700">{item.meaning}</dd><StudyCitations sources={item.sources} /></div>
                ))}
              </dl>
            </div>
          )}
          {body.simple_explanations.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-900">Explained simply</h4>
              <div className="space-y-2 text-sm">
                {body.simple_explanations.map((item, index) => (
                  <div key={index}><p className="font-semibold text-slate-900">{item.concept}</p>
                    <p className="text-slate-700">{item.explanation}</p><StudyCitations sources={item.sources} /></div>
                ))}
              </div>
            </div>
          )}
          {body.chapters.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-900">Chapters</h4>
              <div className="space-y-2 text-sm">
                {body.chapters.map((chapter, index) => (
                  <div key={index}><p className="font-semibold text-slate-900">{chapter.title}</p>
                    <p className="text-slate-700">{chapter.summary}</p><StudyCitations sources={chapter.sources} /></div>
                ))}
              </div>
            </div>
          )}
          <div>
            <button type="button" onClick={() => remove(openNote.id)}
              className="rounded-lg border border-rose-300 px-3 py-1.5 text-sm text-rose-700">Delete these notes</button>
          </div>
        </article>
      )}
    </section>
  )
}
