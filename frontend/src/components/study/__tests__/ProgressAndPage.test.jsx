import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ProgressPanel from '../ProgressPanel'
import Study from '../../../pages/Study'

const mocks = vi.hoisted(() => ({
  api: {
    studyProgress: vi.fn(),
  },
  getErrorMessage: (error, fallback) => (error && error.message) || fallback,
  state: {},
}))
vi.mock('../../../services/api', () => mocks)
vi.mock('../../../context/ChatContext', () => ({ useAppState: () => mocks.state }))

const PROGRESS = {
  total_attempts: 2,
  questions_answered: 8,
  overall_accuracy: 75,
  attempts: [
    { id: 2, quiz_id: 7, quiz_title: 'Quiz (4 questions) from manual.pdf', total: 4, correct: 4, percent: 100, created_at: '2026-11-15T10:00:00' },
    { id: 1, quiz_id: 7, quiz_title: 'Quiz (4 questions) from manual.pdf', total: 4, correct: 2, percent: 50, created_at: '2026-11-15T09:00:00' },
  ],
  topics: [
    { topic: 'Warranty', attempted: 4, correct: 4, accuracy: 100 },
    { topic: 'Cleaning', attempted: 4, correct: 2, accuracy: 50 },
  ],
  weak_topics: [{ topic: 'Cleaning', attempted: 4, correct: 2, accuracy: 50 }],
  flashcard_decks: [{ id: 3, title: 'Flashcards (2)', total: 2, studied: 1 }],
}

describe('ProgressPanel', () => {
  beforeEach(() => {
    mocks.api.studyProgress.mockReset()
  })

  it('shows an encouraging empty state before any quiz is taken', async () => {
    mocks.api.studyProgress.mockResolvedValue({ total_attempts: 0, questions_answered: 0, overall_accuracy: null, attempts: [], topics: [], weak_topics: [], flashcard_decks: [] })
    render(<ProgressPanel />)

    expect(await screen.findByText(/No quiz attempts yet/)).toBeInTheDocument()
  })

  it('shows accuracy, weak topics, topic bars, history and flashcard progress', async () => {
    mocks.api.studyProgress.mockResolvedValue(PROGRESS)
    render(<ProgressPanel />)

    expect(await screen.findByText('75%')).toBeInTheDocument()
    expect(screen.getByText('Cleaning: 50% (2 of 4 correct)')).toBeInTheDocument()
    expect(screen.getAllByText('Quiz (4 questions) from manual.pdf')).toHaveLength(2)
    expect(screen.getByRole('meter', { name: 'Cleaning accuracy' })).toHaveAttribute('aria-valuenow', '50')
    expect(screen.getByText('Flashcards (2): 1 of 2 studied')).toBeInTheDocument()
  })

  it('reloads progress when the refresh key changes (after a new quiz is graded)', async () => {
    mocks.api.studyProgress.mockResolvedValue(PROGRESS)
    const { rerender } = render(<ProgressPanel refreshKey={0} />)
    await screen.findByText('75%')

    rerender(<ProgressPanel refreshKey={1} />)

    await waitFor(() => expect(mocks.api.studyProgress).toHaveBeenCalledTimes(2))
  })

  it('shows a clear error when progress cannot be loaded', async () => {
    mocks.api.studyProgress.mockRejectedValue(new Error('Backend offline'))
    render(<ProgressPanel />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Backend offline')
  })
})

describe('Study page', () => {
  beforeEach(() => {
    mocks.state.documents = [
      { id: 'd1', filename: 'a.pdf', processing_status: 'ready' },
      { id: 'd2', filename: 'b.pdf', processing_status: 'ready' },
    ]
    mocks.state.selectedDocumentIds = []
    mocks.api.studyProgress.mockResolvedValue({ total_attempts: 0, questions_answered: 0, overall_accuracy: null, attempts: [], topics: [], weak_topics: [], flashcard_decks: [] })
  })

  it('shows which PDFs will be studied (all ready PDFs when none are selected)', () => {
    render(<MemoryRouter><Study /></MemoryRouter>)
    expect(screen.getByTestId('study-scope')).toHaveTextContent('All 2 ready PDFs')
  })

  it('shows the selected PDF count when some are selected', () => {
    mocks.state.selectedDocumentIds = ['d2']
    render(<MemoryRouter><Study /></MemoryRouter>)
    expect(screen.getByTestId('study-scope')).toHaveTextContent('1 selected PDF')
  })

  it('shows the six simple study tools and switches between them', async () => {
    render(<MemoryRouter><Study /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Study notes' })).toBeInTheDocument()
    for (const name of ['Study Notes', 'Quiz', 'Flashcards', 'Mock Exam', 'Explain a Topic', 'Important Questions']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
    expect(screen.queryByRole('button', { name: /^Progress$/ })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Quiz' }))
    expect(await screen.findByRole('heading', { name: 'Quiz' })).toBeInTheDocument()
  })
})
