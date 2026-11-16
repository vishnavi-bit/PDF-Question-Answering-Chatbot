import { useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { api, getErrorMessage } from '../../services/api'
import { StudyError, StudyLoading } from './StudyMessage'

function accuracyColor(value) {
  if (value >= 80) return 'bg-emerald-500'
  if (value >= 60) return 'bg-amber-500'
  return 'bg-rose-500'
}

function formatDate(value) {
  if (!value) return ''
  const date = new Date(value.endsWith('Z') ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString()
}

/** Quiz history, accuracy by topic, weak topics, and flashcard progress. */
export default function ProgressPanel({ refreshKey = 0 }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api
      .studyProgress()
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'Your progress could not be loaded.'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  if (loading) return <StudyLoading label="Loading your progress…" />
  if (error) return <StudyError message={error} />
  if (!data) return null

  if (data.total_attempts === 0) {
    return (
      <section aria-labelledby="progress-heading" className="space-y-3">
        <h2 id="progress-heading" className="text-lg font-semibold text-slate-900">Study progress</h2>
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
          No quiz attempts yet. Take a quiz and your scores, accuracy and weak topics will appear here.
        </p>
      </section>
    )
  }

  return (
    <section aria-labelledby="progress-heading" className="space-y-6">
      <h2 id="progress-heading" className="text-lg font-semibold text-slate-900">Study progress</h2>

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Quiz attempts" value={data.total_attempts} />
        <Stat label="Questions answered" value={data.questions_answered} />
        <Stat label="Overall accuracy" value={data.overall_accuracy === null ? '–' : `${data.overall_accuracy}%`} />
      </div>

      {data.weak_topics.length > 0 ? (
        <article className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
          <h3 className="mb-2 flex items-center gap-2 font-semibold text-amber-900">
            <AlertTriangle size={18} aria-hidden="true" /> Topics to practise
          </h3>
          <ul className="space-y-1 text-sm text-amber-900">
            {data.weak_topics.map((topic) => (
              <li key={topic.topic}>
                {topic.topic}: {topic.accuracy}% ({topic.correct} of {topic.attempted} correct)
              </li>
            ))}
          </ul>
        </article>
      ) : (
        <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">No weak topics so far. Keep it up!</p>
      )}

      {data.topics.length > 0 && (
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 font-semibold text-slate-900">Accuracy by topic</h3>
          <ul className="space-y-3">
            {data.topics.map((topic) => (
              <li key={topic.topic}>
                <div className="flex justify-between text-sm text-slate-700">
                  <span>{topic.topic}</span>
                  <span>{topic.accuracy}%</span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100" role="meter" aria-label={`${topic.topic} accuracy`} aria-valuenow={topic.accuracy} aria-valuemin={0} aria-valuemax={100}>
                  <div className={`h-full rounded-full ${accuracyColor(topic.accuracy)}`} style={{ width: `${topic.accuracy}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </article>
      )}

      <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="mb-3 font-semibold text-slate-900">Quiz history</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-2 pr-3 font-semibold">Quiz</th>
                <th className="py-2 pr-3 font-semibold">Score</th>
                <th className="py-2 pr-3 font-semibold">Accuracy</th>
                <th className="py-2 font-semibold">When</th>
              </tr>
            </thead>
            <tbody>
              {data.attempts.map((attempt) => (
                <tr key={attempt.id} className="border-t border-slate-100">
                  <td className="py-2 pr-3 text-slate-700">{attempt.quiz_title}</td>
                  <td className="py-2 pr-3">{attempt.correct} / {attempt.total}</td>
                  <td className="py-2 pr-3">{attempt.percent}%</td>
                  <td className="py-2 text-slate-500">{formatDate(attempt.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      {data.flashcard_decks.length > 0 && (
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-3 font-semibold text-slate-900">Flashcards studied</h3>
          <ul className="space-y-1 text-sm text-slate-700">
            {data.flashcard_decks.map((deck) => (
              <li key={deck.id}>{deck.title}: {deck.studied} of {deck.total} studied</li>
            ))}
          </ul>
        </article>
      )}
    </section>
  )
}

function Stat({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  )
}
