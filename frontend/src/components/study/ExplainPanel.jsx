import { useState } from 'react'
import { Lightbulb } from 'lucide-react'
import { api, getErrorMessage } from '../../services/api'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

/** Explain a topic in simple words, with an example, using only your PDF. */
export default function ExplainPanel({ documentIds }) {
  const [topic, setTopic] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const explain = async (event) => {
    event.preventDefault()
    const cleaned = topic.trim()
    if (cleaned.length < 2) {
      setError('Type a topic of at least two letters.')
      return
    }
    setLoading(true)
    setError('')
    try {
      setResult(await api.explainTopic({ topic: cleaned, document_ids: documentIds }))
    } catch (err) {
      setResult(null)
      setError(getErrorMessage(err, 'The topic could not be explained.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section aria-labelledby="explain-heading" className="space-y-5">
      <div>
        <h2 id="explain-heading" className="text-lg font-semibold text-slate-900">Explain a topic</h2>
        <p className="text-sm text-slate-500">Type a topic from your PDF.</p>
      </div>

      <form onSubmit={explain} className="flex flex-wrap gap-2">
        <label htmlFor="explain-topic" className="sr-only">Topic to explain</label>
        <input
          id="explain-topic"
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder="For example: warranty"
          maxLength={200}
          className="min-w-0 flex-1 rounded-xl border border-slate-300 px-4 py-2.5 text-sm focus:border-indigo-400 focus:outline-none focus:ring-4 focus:ring-indigo-100"
        />
        <button
          type="submit"
          disabled={loading}
          className="brand-gradient rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-200 disabled:opacity-50"
        >
          Explain
        </button>
      </form>

      {loading && <StudyLoading label="Reading your PDF…" />}
      <StudyError message={error} />

      {result && !result.found && (
        <p role="status" className="rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800">{result.message}</p>
      )}

      {result && result.found && (
        <article className="animate-fade-up space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm" data-testid="explain-result">
          <h3 className="text-base font-semibold text-slate-900">{result.topic}</h3>
          <p className="text-sm leading-7 text-slate-700">{result.explanation}</p>
          {result.example && (
            <div className="flex gap-3 rounded-xl bg-emerald-50 p-4">
              <Lightbulb size={18} className="mt-0.5 shrink-0 text-emerald-600" aria-hidden="true" />
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Example</p>
                <p className="text-sm text-slate-700">{result.example}</p>
              </div>
            </div>
          )}
          <StudyCitations sources={result.sources} />
        </article>
      )}
    </section>
  )
}
