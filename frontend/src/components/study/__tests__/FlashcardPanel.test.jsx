import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import FlashcardPanel from '../FlashcardPanel'

const mocks = vi.hoisted(() => ({
  api: {
    createFlashcards: vi.fn(),
    setFlashcardReview: vi.fn(),
    documentFileUrl: (id) => `/api/documents/${id}/file`,
  },
  getErrorMessage: (error, fallback) => (error && error.message) || fallback,
}))
vi.mock('../../../services/api', () => mocks)

const SOURCE = { source_id: 'S1', document_id: 'd1', filename: 'manual.pdf', page_number: 4 }
const DECK = {
  id: 5,
  title: 'Flashcards (2) from manual.pdf',
  document_ids: ['d1'],
  studied_indices: [],
  cards: [
    { index: 0, question: 'What is the warranty?', answer: 'Two years.', sources: [SOURCE], status: 'new', due_date: null },
    { index: 1, question: 'How is the blade cleaned?', answer: 'With warm water.', sources: [SOURCE], status: 'new', due_date: null },
  ],
}

async function openDeck() {
  mocks.api.createFlashcards.mockResolvedValue(DECK)
  render(<FlashcardPanel documentIds={['d1']} />)
  fireEvent.click(screen.getByRole('button', { name: 'Create Flashcards' }))
  await screen.findByTestId('card-face')
}

beforeEach(() => {
  mocks.api.createFlashcards.mockReset()
  mocks.api.setFlashcardReview.mockReset()
})

describe('FlashcardPanel', () => {
  it('shows the question first and flips the card to the answer', async () => {
    await openDeck()
    expect(screen.getByTestId('card-face')).toHaveTextContent('What is the warranty?')
    fireEvent.click(screen.getByRole('button', { name: 'Show the answer' }))
    expect(screen.getByTestId('card-face')).toHaveTextContent('Two years.')
    expect(screen.getAllByText(/manual\.pdf/).length).toBeGreaterThan(0)
  })

  it('moves Next and Previous, and disables Previous on the first card', async () => {
    await openDeck()
    expect(screen.getByRole('button', { name: /Previous/ })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(screen.getByTestId('deck-progress')).toHaveTextContent('Card 2 of 2')
    expect(screen.getByTestId('card-face')).toHaveTextContent('How is the blade cleaned?')
    fireEvent.click(screen.getByRole('button', { name: /Previous/ }))
    expect(screen.getByTestId('deck-progress')).toHaveTextContent('Card 1 of 2')
  })

  it('marks a card as Known and shows the new status', async () => {
    await openDeck()
    mocks.api.setFlashcardReview.mockResolvedValue({ card_index: 0, status: 'known', due_date: '2026-11-17', interval_days: 1, ease_factor: 2.5, repetitions: 1 })
    fireEvent.click(screen.getByRole('button', { name: 'Known' }))
    await waitFor(() => expect(mocks.api.setFlashcardReview).toHaveBeenCalledWith(5, 0, 'known'))
    expect(await screen.findByTestId('card-status')).toHaveTextContent('Known')
  })

  it('marks a card as Need Practice', async () => {
    await openDeck()
    mocks.api.setFlashcardReview.mockResolvedValue({ card_index: 0, status: 'need_practice', due_date: '2026-11-17', interval_days: 1, ease_factor: 2.3, repetitions: 0 })
    fireEvent.click(screen.getByRole('button', { name: 'Need Practice' }))
    await waitFor(() => expect(mocks.api.setFlashcardReview).toHaveBeenCalledWith(5, 0, 'need_practice'))
    expect(await screen.findByTestId('card-status')).toHaveTextContent('Need Practice')
  })

  it('shows an error when the mark cannot be saved', async () => {
    await openDeck()
    mocks.api.setFlashcardReview.mockRejectedValue(new Error('Your choice could not be saved right now.'))
    fireEvent.click(screen.getByRole('button', { name: 'Known' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Your choice could not be saved right now.')
  })

  it('keeps the screen simple: no separate "mark as studied" toggle', async () => {
    await openDeck()
    expect(screen.queryByRole('button', { name: /studied/i })).toBeNull()
  })
})
