import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import QuizPanel from '../QuizPanel'

const mocks = vi.hoisted(() => ({
  api: {
    createQuiz: vi.fn(),
    submitQuiz: vi.fn(),
    documentFileUrl: (id) => `/api/documents/${id}/file`,
  },
  getErrorMessage: (error, fallback) => (error && error.message) || fallback,
}))
vi.mock('../../../services/api', () => mocks)

const QUIZ = {
  id: 7,
  title: 'Quiz (2 questions) from manual.pdf',
  document_ids: ['d1'],
  questions: [
    { index: 0, question: 'What is covered?', options: ['Motor', 'Paint', 'Cord', 'Lid'], topic: 'Warranty' },
    { index: 1, question: 'How to clean?', options: ['Water', 'Oil', 'Sand', 'Wax'], topic: 'Cleaning' },
  ],
}

const GRADED = {
  attempt_id: 1,
  total: 2,
  correct: 1,
  percent: 50,
  items: [
    {
      index: 0,
      question: 'What is covered?',
      options: ['Motor', 'Paint', 'Cord', 'Lid'],
      chosen: 0,
      correct_index: 0,
      is_correct: true,
      explanation: 'The warranty covers the motor.',
      topic: 'Warranty',
      sources: [{ source_id: 'S1', document_id: 'd1', filename: 'manual.pdf', page_number: 3 }],
    },
    {
      index: 1,
      question: 'How to clean?',
      options: ['Water', 'Oil', 'Sand', 'Wax'],
      chosen: null,
      correct_index: 0,
      is_correct: false,
      explanation: 'Use warm water.',
      topic: 'Cleaning',
      sources: [],
    },
  ],
}

beforeEach(() => {
  mocks.api.createQuiz.mockReset()
  mocks.api.submitQuiz.mockReset()
})

async function startQuiz() {
  mocks.api.createQuiz.mockResolvedValue(QUIZ)
  render(<QuizPanel documentIds={['d1']} />)
  fireEvent.click(screen.getByRole('button', { name: 'Generate Quiz' }))
  await screen.findByText(/What is covered\?/)
}

describe('QuizPanel (simplified)', () => {
  it('offers 5, 10 or 20 questions and creates a medium quiz for the selected PDFs', async () => {
    await startQuiz()
    expect(mocks.api.createQuiz).toHaveBeenCalledWith({ count: 5, difficulty: 'medium', document_ids: ['d1'] })
  })

  it('sends the count the student chooses', async () => {
    mocks.api.createQuiz.mockResolvedValue(QUIZ)
    render(<QuizPanel documentIds={['d1']} />)
    const select = screen.getByLabelText('Number of quiz questions')
    expect([...select.options].map((option) => option.value)).toEqual(['5', '10', '20'])
    fireEvent.change(select, { target: { value: '10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate Quiz' }))
    await waitFor(() => expect(mocks.api.createQuiz).toHaveBeenCalledWith({ count: 10, difficulty: 'medium', document_ids: ['d1'] }))
  })

  it('does not allow submitting before any question is answered', async () => {
    await startQuiz()
    expect(screen.getByRole('button', { name: 'Submit answers' })).toBeDisabled()
  })

  it('submits the answers and shows the score, explanation and page citation', async () => {
    await startQuiz()
    mocks.api.submitQuiz.mockResolvedValue(GRADED)
    fireEvent.click(screen.getByLabelText(/Motor/))
    fireEvent.click(screen.getByRole('button', { name: 'Submit answers' }))
    expect(await screen.findByTestId('score')).toHaveTextContent('1 of 2 correct')
    expect(screen.getByText('The warranty covers the motor.')).toBeInTheDocument()
    expect(screen.getAllByText(/manual\.pdf/).length).toBeGreaterThan(0)
    expect(mocks.api.submitQuiz).toHaveBeenCalledWith(7, [0, null])
    expect(screen.queryByRole('button', { name: /Download/ })).toBeNull()
  })

  it('shows a clear message when the quiz cannot be created', async () => {
    mocks.api.createQuiz.mockRejectedValue(new Error('Gemini free-tier quota is used up for now.'))
    render(<QuizPanel documentIds={[]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Generate Quiz' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('free-tier quota is used up')
  })
})
