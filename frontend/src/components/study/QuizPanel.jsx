import { useState } from 'react'
import { CheckCircle2, XCircle } from 'lucide-react'
import { api, getErrorMessage } from '../../services/api'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

const LETTERS = ['A', 'B', 'C', 'D']
const COUNTS = [5, 10, 20]

/** Quiz: choose 5, 10 or 20 questions, answer them, and see your score. */
export default function QuizPanel({ documentIds, onAttemptSaved }) {
  const [count, setCount] = useState(5)
  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    setAnswers({})
    try {
      setQuiz(await api.createQuiz({ count, difficulty: 'medium', document_ids: documentIds }))
    } catch (err) {
      setQuiz(null)
      setError(getErrorMessage(err, 'The quiz could not be created.'))
    } finally {
      setLoading(false)
    }
  }

  const submit = async () => {
    setLoading(true)
    setError('')
    const list = quiz.questions.map((_, index) => (answers[index] === undefined ? null : answers[index]))
    try {
      const graded = await api.submitQuiz(quiz.id, list)
      setResult(graded)
      if (onAttemptSaved) onAttemptSaved(graded)
    } catch (err) {
      setError(getErrorMessage(err, 'Your answers could not be checked. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  const answeredCount = Object.keys(answers).length

  return (
    <section aria-labelledby="quiz-heading" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="quiz-heading" className="text-lg font-semibold text-slate-900">Quiz</h2>
          <p className="text-sm text-slate-500">Choose how many questions you want, then answer them.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="text-sm text-slate-600">
            Questions
            <select
              aria-label="Number of quiz questions"
              value={count}
              onChange={(event) => setCount(Number(event.target.value))}
              className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              {COUNTS.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <button
            type="button"
            onClick={generate}
            disabled={loading}
            className="brand-gradient rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-200 disabled:opacity-50"
          >
            {quiz ? 'New quiz' : 'Generate Quiz'}
          </button>
        </div>
      </div>

      {loading && <StudyLoading label={quiz ? 'Checking your answers…' : undefined} />}
      <StudyError message={error} />

      {quiz && !result && (
        <div className="space-y-4">
          <p className="text-sm text-slate-500">{answeredCount} of {quiz.questions.length} answered</p>
          {quiz.questions.map((question) => (
            <fieldset key={question.index} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <legend className="px-1 text-sm font-semibold text-slate-900">
                {question.index + 1}. {question.question}
              </legend>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {question.options.map((option, optionIndex) => (
                  <label
                    key={optionIndex}
                    className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm transition ${
                      answers[question.index] === optionIndex ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-indigo-300'
                    }`}
                  >
                    <input
                      type="radio"
                      name={`question-${question.index}`}
                      checked={answers[question.index] === optionIndex}
                      onChange={() => setAnswers({ ...answers, [question.index]: optionIndex })}
                      className="accent-indigo-600"
                    />
                    <span><strong>{LETTERS[optionIndex]}.</strong> {option}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
          <button
            type="button"
            onClick={submit}
            disabled={loading || answeredCount === 0}
            className="rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            Submit answers
          </button>
        </div>
      )}

      {result && (
        <div className="space-y-4" data-testid="quiz-result">
          <div className="rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 p-5 text-white shadow-md">
            <p className="text-sm opacity-90">Your score</p>
            <p className="text-3xl font-bold" data-testid="score">{result.correct} of {result.total} correct</p>
            <p className="text-sm opacity-90">{result.percent}%</p>
          </div>
          {result.items.map((item) => (
            <article key={item.index} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="flex items-start gap-2 text-sm font-semibold text-slate-900">
                {item.is_correct ? (
                  <CheckCircle2 size={18} className="mt-0.5 shrink-0 text-emerald-600" aria-label="Correct" />
                ) : (
                  <XCircle size={18} className="mt-0.5 shrink-0 text-rose-600" aria-label="Incorrect" />
                )}
                {item.index + 1}. {item.question}
              </h3>
              <p className="mt-2 text-sm text-slate-700">
                Your answer: {item.chosen === null ? 'No answer' : `${LETTERS[item.chosen]}. ${item.options[item.chosen]}`}
              </p>
              <p className="text-sm text-emerald-700">
                Correct answer: {LETTERS[item.correct_index]}. {item.options[item.correct_index]}
              </p>
              <p className="mt-2 text-sm text-slate-600">{item.explanation}</p>
              <StudyCitations sources={item.sources} />
            </article>
          ))}
          <button type="button" onClick={generate} className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700">
            Try another quiz
          </button>
        </div>
      )}
    </section>
  )
}
