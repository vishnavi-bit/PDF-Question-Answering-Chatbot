import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api, getErrorMessage } from '../../services/api'
import StudyCitations from './StudyCitations'
import { StudyError, StudyLoading } from './StudyMessage'

const COUNTS = [5, 10, 20]
const STATUS_LABELS = { known: 'Known', need_practice: 'Need Practice', new: 'Not marked yet' }

/** Flashcards: flip a card to see the answer, then mark it Known or Need Practice. */
export default function FlashcardPanel({ documentIds }) {
  const [count, setCount] = useState(10)
  const [deck, setDeck] = useState(null)
  const [position, setPosition] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      setDeck(await api.createFlashcards({ count, document_ids: documentIds }))
      setPosition(0)
      setFlipped(false)
    } catch (err) {
      setDeck(null)
      setError(getErrorMessage(err, 'The flashcards could not be created.'))
    } finally {
      setLoading(false)
    }
  }

  const go = (next) => {
    setPosition(next)
    setFlipped(false)
  }

  const markCard = async (status) => {
    const current = deck.cards[position]
    try {
      const saved = await api.setFlashcardReview(deck.id, current.index, status)
      const cards = deck.cards.map((item) => (item.index === current.index ? { ...item, ...saved } : item))
      setDeck({ ...deck, cards })
    } catch (err) {
      setError(getErrorMessage(err, 'Your choice could not be saved.'))
    }
  }

  const card = deck ? deck.cards[position] : null
  const status = card ? card.status || 'new' : 'new'

  return (
    <section aria-labelledby="flash-heading" className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="flash-heading" className="text-lg font-semibold text-slate-900">Flashcards</h2>
          <p className="text-sm text-slate-500">Read the question, flip the card, then mark it.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="text-sm text-slate-600">
            Cards
            <select
              aria-label="Number of flashcards"
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
            {deck ? 'New cards' : 'Create Flashcards'}
          </button>
        </div>
      </div>

      {loading && <StudyLoading />}
      <StudyError message={error} />

      {card && (
        <div className="space-y-4">
          <p className="text-sm text-slate-500" data-testid="deck-progress">Card {position + 1} of {deck.cards.length}</p>

          <button
            type="button"
            onClick={() => setFlipped((value) => !value)}
            aria-pressed={flipped}
            aria-label={flipped ? 'Show the question' : 'Show the answer'}
            className="flex min-h-[200px] w-full flex-col justify-center rounded-3xl border border-indigo-200 bg-white p-6 text-center shadow-md transition hover:shadow-lg"
          >
            <span className="mb-3 text-xs font-semibold uppercase tracking-wide text-indigo-600">
              {flipped ? 'Answer' : 'Question'}
            </span>
            <span className="text-lg font-medium text-slate-900" data-testid="card-face">
              {flipped ? card.answer : card.question}
            </span>
            <span className="mt-4 text-sm text-slate-500">Click to {flipped ? 'see the question' : 'see the answer'}</span>
          </button>
          {flipped && <StudyCitations sources={card.sources} />}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-600">
              This card: <span className="font-semibold" data-testid="card-status">{STATUS_LABELS[status] || status}</span>
            </p>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Mark this card">
              <button type="button" onClick={() => markCard('known')}
                className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white">
                Known
              </button>
              <button type="button" onClick={() => markCard('need_practice')}
                className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-white">
                Need Practice
              </button>
            </div>
          </div>

          <div className="flex gap-2">
            <button type="button" onClick={() => go(position - 1)} disabled={position === 0}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-300 px-4 py-2 text-sm disabled:opacity-40">
              <ChevronLeft size={16} aria-hidden="true" /> Previous
            </button>
            <button type="button" onClick={() => go(position + 1)} disabled={position === deck.cards.length - 1}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-300 px-4 py-2 text-sm disabled:opacity-40">
              Next <ChevronRight size={16} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
