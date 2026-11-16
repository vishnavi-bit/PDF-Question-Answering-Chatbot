import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, getErrorMessage } from '../../services/api'
import ExportButton from './ExportButton'
import StudyCitations from './StudyCitations'
import { StudyError } from './StudyMessage'

/** Maps a learning-path step to the Study tab it refers to. */
const ACTION_TABS = { quiz: 'quiz', notes: 'notes', revision: 'revision', mock: 'mock' }

/**
 * Revision planner, learning path and saved questions.
 * Everything shown comes from data recorded in this app (reviews, quiz results, saved questions).
 */
export default function RevisionPanel({ onNavigate }) {
  const [today, setToday] = useState(null)
  const [upcoming, setUpcoming] = useState(null)
  const [path, setPath] = useState(null)
  const [decks, setDecks] = useState([])
  const [deckId, setDeckId] = useState('')
  const [saved, setSaved] = useState([])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setError('')
    try {
      const [todayData, upcomingData, pathData, progress, savedData] = await Promise.all([
        api.revisionToday(),
        api.revisionUpcoming(7),
        api.learningPath(),
        api.studyProgress(),
        api.listSavedQuestions(),
      ])
      setToday(todayData)
      setUpcoming(upcomingData)
      setPath(pathData)
      setDecks(progress.flashcard_decks)
      setSaved(savedData.questions)
      setDeckId((current) => current || (progress.flashcard_decks[0] ? String(progress.flashcard_decks[0].id) : ''))
    } catch (err) {
      setError(getErrorMessage(err, 'The revision data could not be loaded.'))
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const createPlan = async () => {
    if (!deckId) return
    setError('')
    try {
      await api.createRevisionPlan(Number(deckId))
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The revision plan could not be created.'))
    }
  }

  const toggleTask = async (task) => {
    setError('')
    try {
      await api.completeRevisionTask(task.id, !task.completed)
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The task could not be updated.'))
    }
  }

  const removeQuestion = async (id) => {
    if (!window.confirm('Remove this saved question?')) return
    try {
      await api.deleteSavedQuestion(id)
      refresh()
    } catch (err) {
      setError(getErrorMessage(err, 'The question could not be removed.'))
    }
  }

  return (
    <section aria-labelledby="revision-heading" className="space-y-6">
      <div>
        <h2 id="revision-heading" className="text-lg font-semibold text-slate-900">Revision and learning path</h2>
        <p className="text-sm text-slate-500">Plans and due dates come from your flashcard reviews. The learning path uses only your recorded quiz results.</p>
      </div>
      <StudyError message={error} />

      <div className="grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="font-semibold text-slate-900">Today</h3>
          {today ? (
            <>
              <p className="mt-1 text-sm text-slate-600" data-testid="due-count">
                {today.due_card_count} flashcard{today.due_card_count === 1 ? '' : 's'} due · {today.open_task_count} open task{today.open_task_count === 1 ? '' : 's'}
              </p>
              {today.cards.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                  {today.cards.slice(0, 10).map((card, index) => (
                    <li key={`${card.deck_id}-${card.card_index}-${index}`}>{card.question || `Card ${card.card_index + 1} of deck ${card.deck_id}`}</li>
                  ))}
                </ul>
              )}
            </>
          ) : <p className="mt-1 text-sm text-slate-500">Loading…</p>}
          {today && today.tasks.length > 0 && (
            <ul className="mt-3 space-y-2" aria-label="Revision tasks">
              {today.tasks.map((task) => (
                <li key={task.id} className="flex items-center justify-between gap-2 text-sm">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={task.completed} onChange={() => toggleTask(task)} className="accent-indigo-600" />
                    <span className={task.completed ? 'text-slate-500 line-through' : 'text-slate-800'}>
                      {task.title} · due {task.due_date}{task.overdue && !task.completed ? ' (overdue)' : ''}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="font-semibold text-slate-900">Make a revision plan</h3>
          <p className="mt-1 text-sm text-slate-500">Creates reviews on days 1, 3, 7 and 14 for a flashcard deck.</p>
          {decks.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500">Create flashcards first, then you can plan their revision here.</p>
          ) : (
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <label className="text-sm text-slate-600">
                Deck
                <select aria-label="Flashcard deck for the plan" value={deckId} onChange={(e) => setDeckId(e.target.value)}
                  className="ml-2 rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm">
                  {decks.map((deck) => <option key={deck.id} value={deck.id}>{deck.title}</option>)}
                </select>
              </label>
              <button type="button" onClick={createPlan}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Create plan</button>
            </div>
          )}
          {upcoming && upcoming.tasks.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm text-slate-700" aria-label="Upcoming revision tasks">
              {upcoming.tasks.map((task) => <li key={task.id}>{task.due_date}: {task.title}</li>)}
            </ul>
          )}
        </article>
      </div>

      {path && (
        <article className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="learning-path">
          <h3 className="font-semibold text-slate-900">Learning path</h3>
          <p className="text-sm text-slate-500">
            {path.has_quiz_data
              ? `${path.quiz_attempts} quiz attempt${path.quiz_attempts === 1 ? '' : 's'} · ${path.questions_answered} questions · overall ${path.overall_accuracy}%`
              : 'No quiz results yet.'}
          </p>
          <ol className="space-y-2">
            {path.steps.map((step, index) => (
              <li key={index} className="rounded-xl bg-slate-50 p-3">
                <p className="text-sm font-semibold text-slate-900">{step.title}</p>
                <p className="text-sm text-slate-600">{step.detail}</p>
                {ACTION_TABS[step.action] && (
                  <button type="button" onClick={() => onNavigate && onNavigate(ACTION_TABS[step.action])}
                    className="mt-2 rounded-lg border border-indigo-300 px-3 py-1 text-sm text-indigo-700">Go there</button>
                )}
                {step.action === 'documents' && (
                  <Link to="/" className="mt-2 inline-block text-sm font-medium text-indigo-700">Upload a PDF</Link>
                )}
              </li>
            ))}
          </ol>
          <p className="text-xs text-slate-500">{path.note}</p>
        </article>
      )}

      <article className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-slate-900">Saved questions ({saved.length})</h3>
          {saved.length > 0 && <ExportButton kind="saved-questions" label="Download PDF" />}
        </div>
        {saved.length === 0 ? (
          <p className="text-sm text-slate-500">Save important questions from the Exam questions tab to revise them here.</p>
        ) : (
          <ul className="space-y-3">
            {saved.map((item) => (
              <li key={item.id} className="rounded-xl border border-slate-100 p-3">
                <p className="text-sm font-semibold text-slate-900">{item.question}</p>
                {item.answer && <p className="mt-1 text-sm text-slate-700">{item.answer}</p>}
                <StudyCitations sources={item.sources} />
                <button type="button" onClick={() => removeQuestion(item.id)}
                  className="mt-2 rounded-lg border border-rose-300 px-3 py-1 text-sm text-rose-700">Remove</button>
              </li>
            ))}
          </ul>
        )}
      </article>
    </section>
  )
}
