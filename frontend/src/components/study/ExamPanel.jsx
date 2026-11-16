import { useState } from 'react'
import { api, getErrorMessage } from '../../services/api'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

const TYPES = [
  { value: 'short', label: 'Short Answer', short: 5, long: 0 },
  { value: 'long', label: 'Long Answer', short: 0, long: 3 },
]

/** Important questions: choose Short Answer or Long Answer, generate them, and show each answer when you want. */
export default function ExamPanel({ documentIds }) {
  const [type, setType] = useState('short')
  const [questions, setQuestions] = useState(null)
  const [shown, setShown] = useState({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    const chosen = TYPES.find((item) => item.value === type)
    setLoading(true)
    setError('')
    setShown({})
    try {
      const paper = await api.createExam({ short_count: chosen.short, long_count: chosen.long, document_ids: documentIds })
      setQuestions(paper.questions)
    } catch (err) {
      setQuestions(null)
      setError(getErrorMessage(err, 'The questions could not be created.'))
    } finally {
      setLoading(false)
    }
  }

  const toggle = (index) => setShown((current) => ({ ...current, [index]: !current[index] }))

  return (
    <section aria-labelledby="exam-heading" className="space-y-5">
      <div>
        <h2 id="exam-heading" className="text-lg font-semibold text-slate-900">Important questions</h2>
        <p className="text-sm text-slate-500">Likely exam questions from your PDF, with answers.</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Question type" className="inline-flex rounded-xl border border-slate-200 bg-white p-1">
          {TYPES.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={type === item.value}
              onClick={() => setType(item.value)}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${type === item.value ? 'bg-indigo-600 text-white' : 'text-slate-600'}`}
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
          Generate Questions
        </button>
      </div>

      {loading && <StudyLoading />}
      <StudyError message={error} />

      {questions && (
        <ol className="space-y-3" data-testid="exam-list">
          {questions.map((question) => (
            <li key={question.index} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="font-medium text-slate-900">{question.index + 1}. {question.question}</p>
              <button
                type="button"
                onClick={() => toggle(question.index)}
                aria-expanded={!!shown[question.index]}
                className="mt-3 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700"
              >
                {shown[question.index] ? 'Hide answer' : 'Show answer'}
              </button>
              {shown[question.index] && (
                <div className="mt-3 border-t border-slate-100 pt-3">
                  <p className="text-sm leading-6 text-slate-700">{question.answer}</p>
                  <StudyCitations sources={question.sources} />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
