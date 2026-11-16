import { useEffect, useRef, useState } from 'react'
import { Timer } from 'lucide-react'
import { api, getErrorMessage } from '../../services/api'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

const LETTERS = ['A', 'B', 'C', 'D']
const QUESTIONS = 10
const DURATIONS = [10, 20, 30, 60]

/** Format remaining seconds as m:ss. */
export function formatRemaining(totalSeconds) {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(safe / 60)
  const seconds = safe % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/**
 * Mock exam: pick a difficulty and a time, start, answer, submit, and see your score.
 * The server sets the deadline and grades the answers. When time runs out, the answers are sent automatically.
 */
export default function MockExamPanel({ documentIds }) {
  const [difficulty, setDifficulty] = useState('medium')
  const [minutes, setMinutes] = useState(20)
  const [exam, setExam] = useState(null)
  const [attempt, setAttempt] = useState(null)
  const [answers, setAnswers] = useState([])
  const [result, setResult] = useState(null)
  const [now, setNow] = useState(Date.now())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const submittingRef = useRef(false)

  const deadlineMs = attempt ? new Date(attempt.deadline).getTime() : null
  const remainingSeconds = deadlineMs ? (deadlineMs - now) / 1000 : null
  const inProgress = Boolean(attempt && !result)

  useEffect(() => {
    if (!inProgress) return undefined
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [inProgress])

  const submit = async (autoSubmitted) => {
    if (!attempt || submittingRef.current) return
    submittingRef.current = true
    setLoading(true)
    setError('')
    try {
      const graded = await api.submitMockExam(attempt.attempt_id, {
        answers: exam.mcq.map((_, index) => (answers[index] === undefined ? null : answers[index])),
        descriptive: [],
        auto_submitted: autoSubmitted,
      })
      setResult(graded)
      setAttempt(null)
    } catch (err) {
      submittingRef.current = false
      setError(getErrorMessage(err, 'Your answers could not be submitted. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  // Submit by itself when the time is up.
  useEffect(() => {
    if (inProgress && remainingSeconds !== null && remainingSeconds <= 0) {
      submit(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inProgress, remainingSeconds])

  const start = async () => {
    setLoading(true)
    setError('')
    setResult(null)
    submittingRef.current = false
    try {
      const paper = await api.createMockExam({
        difficulty,
        mcq_count: QUESTIONS,
        descriptive_count: 0,
        duration_minutes: minutes,
        document_ids: documentIds,
      })
      const started = await api.startMockExam(paper.id)
      setExam(paper)
      setAttempt(started)
      setAnswers([])
      setNow(Date.now())
    } catch (err) {
      setExam(null)
      setAttempt(null)
      setError(getErrorMessage(err, 'The mock exam could not be started.'))
    } finally {
      setLoading(false)
    }
  }

  const chooseAnswer = (questionIndex, optionIndex) => {
    setAnswers((current) => {
      const next = [...current]
      next[questionIndex] = optionIndex
      return next
    })
  }

  return (
    <section aria-labelledby="mock-heading" className="space-y-5">
      <div>
        <h2 id="mock-heading" className="text-lg font-semibold text-slate-900">Mock exam</h2>
        <p className="text-sm text-slate-500">Ten multiple-choice questions from your PDF, with a timer.</p>
      </div>

      {!attempt && !result && (
        <form
          aria-label="Set up the mock exam"
          onSubmit={(event) => { event.preventDefault(); start() }}
          className="flex flex-wrap items-end gap-3"
        >
          <label className="text-sm text-slate-600">
            Difficulty
            <select aria-label="Mock exam difficulty" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}
              className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <label className="text-sm text-slate-600">
            Time
            <select aria-label="Exam time" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}
              className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
              {DURATIONS.map((value) => <option key={value} value={value}>{value} minutes</option>)}
            </select>
          </label>
          <button type="submit" disabled={loading}
            className="brand-gradient rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-200 disabled:opacity-50">
            Start Mock Exam
          </button>
        </form>
      )}

      {loading && <StudyLoading label={attempt ? 'Submitting your answers…' : 'Preparing your exam…'} />}
      <StudyError message={error} />

      {attempt && !result && exam && (
        <div className="space-y-5">
          <div className="sticky top-2 z-10 flex items-center gap-3 rounded-2xl bg-slate-900 px-4 py-3 text-white shadow-lg" role="timer" aria-label="Time left">
            <Timer size={18} aria-hidden="true" />
            <span className="font-mono text-lg" data-testid="exam-timer">{formatRemaining(remainingSeconds)}</span>
            <span className="text-sm opacity-80">left</span>
            <button type="button" onClick={() => submit(false)} disabled={loading}
              className="ml-auto rounded-xl bg-white px-4 py-2 text-sm font-semibold text-slate-900 disabled:opacity-50">
              Submit exam
            </button>
          </div>

          <ol className="space-y-4">
            {exam.mcq.map((question) => (
              <li key={question.index} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <fieldset>
                  <legend className="text-sm font-semibold text-slate-900">{question.index + 1}. {question.question}</legend>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {question.options.map((option, optionIndex) => (
                      <label key={optionIndex}
                        className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm ${
                          answers[question.index] === optionIndex ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200'}`}>
                        <input type="radio" name={`exam-mcq-${question.index}`}
                          checked={answers[question.index] === optionIndex}
                          onChange={() => chooseAnswer(question.index, optionIndex)}
                          className="accent-indigo-600" />
                        <span><strong>{LETTERS[optionIndex]}.</strong> {option}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              </li>
            ))}
          </ol>
        </div>
      )}

      {result && (
        <div className="space-y-4" data-testid="mock-result">
          <div className="rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 p-5 text-white shadow-md">
            <p className="text-sm opacity-90">Your final score</p>
            <p className="text-3xl font-bold" data-testid="mock-score">{result.correct} of {result.total_mcq} correct</p>
            <p className="text-sm opacity-90">{result.percent}%</p>
            {result.auto_submitted && <p className="mt-2 text-sm">Time ran out, so your answers were submitted.</p>}
          </div>
          {result.mcq.map((item) => (
            <article key={item.index} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-semibold text-slate-900">{item.index + 1}. {item.question}</p>
              <p className="mt-1 text-sm text-slate-700">
                Your answer: {item.chosen === null ? 'No answer' : `${LETTERS[item.chosen]}. ${item.options[item.chosen]}`}
              </p>
              <p className="text-sm text-emerald-700">Correct answer: {LETTERS[item.correct_index]}. {item.options[item.correct_index]}</p>
              <p className="mt-1 text-sm text-slate-600">{item.explanation}</p>
              <StudyCitations sources={item.sources} />
            </article>
          ))}
          <button type="button" onClick={() => { setResult(null); setExam(null) }}
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700">
            Take another exam
          </button>
        </div>
      )}
    </section>
  )
}
