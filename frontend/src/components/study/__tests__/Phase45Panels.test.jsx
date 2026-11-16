import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import MockExamPanel, { formatRemaining } from '../MockExamPanel'
import MindMapPanel, { clampZoom } from '../MindMapPanel'
import RevisionPanel from '../RevisionPanel'

const mocks = vi.hoisted(() => ({
  api: {
    createMockExam: vi.fn(),
    startMockExam: vi.fn(),
    submitMockExam: vi.fn(),
    listMindMaps: vi.fn(),
    createMindMap: vi.fn(),
    getMindMap: vi.fn(),
    renameMindMap: vi.fn(),
    deleteMindMap: vi.fn(),
    revisionToday: vi.fn(),
    revisionUpcoming: vi.fn(),
    learningPath: vi.fn(),
    studyProgress: vi.fn(),
    listSavedQuestions: vi.fn(),
    deleteSavedQuestion: vi.fn(),
    createRevisionPlan: vi.fn(),
    completeRevisionTask: vi.fn(),
    documentFileUrl: (id) => `/api/documents/${id}/file`,
    exportPdf: vi.fn(),
  },
  getErrorMessage: (error, fallback) => (error && error.message) || fallback,
}))
vi.mock('../../../services/api', () => mocks)

const PAPER = {
  id: 3,
  title: 'Mock exam from manual.pdf',
  difficulty: 'medium',
  duration_minutes: 20,
  document_ids: ['d1'],
  mcq: [{ index: 0, question: 'Warranty length?', options: ['1 year', '2 years', '3 years', '4 years'], topic: 'Warranty' }],
  descriptive: [],
}

beforeEach(() => {
  Object.values(mocks.api).forEach((fn) => {
    if (typeof fn?.mockReset === 'function') fn.mockReset()
  })
  mocks.api.listMindMaps.mockResolvedValue({ mind_maps: [], total: 0 })
  mocks.api.listSavedQuestions.mockResolvedValue({ questions: [], total: 0 })
  mocks.api.studyProgress.mockResolvedValue({ flashcard_decks: [] })
  mocks.api.revisionToday.mockResolvedValue({ date: '2026-11-16', tasks: [], cards: [], open_task_count: 0, due_card_count: 0 })
  mocks.api.revisionUpcoming.mockResolvedValue({ from: '', to: '', tasks: [], cards: [] })
  mocks.api.learningPath.mockResolvedValue({
    has_quiz_data: false, quiz_attempts: 0, questions_answered: 0, overall_accuracy: null,
    weak_topics: [], due_cards: 0, note: 'Only recorded data.',
    steps: [{ type: 'start', title: 'Take a quiz to find your weak topics', detail: 'No quiz data yet.', action: 'quiz' }],
  })
})

describe('pure helpers', () => {
  it('formats remaining time as m:ss and never goes negative', () => {
    expect(formatRemaining(125.9)).toBe('2:05')
    expect(formatRemaining(-3)).toBe('0:00')
    expect(formatRemaining(0)).toBe('0:00')
  })

  it('keeps zoom between 50% and 200%', () => {
    expect(clampZoom(0.1)).toBe(0.5)
    expect(clampZoom(9)).toBe(2)
    expect(clampZoom(1.25)).toBe(1.25)
  })
})

describe('MockExamPanel (simplified)', () => {
  it('starts an exam with the chosen difficulty and time, then submits the answers', async () => {
    mocks.api.createMockExam.mockResolvedValue(PAPER)
    mocks.api.startMockExam.mockResolvedValue({
      attempt_id: 9, exam_id: 3, deadline: new Date(Date.now() + 20 * 60000).toISOString(), duration_seconds: 1200,
    })
    mocks.api.submitMockExam.mockResolvedValue({
      attempt_id: 9, exam_id: 3, exam_title: PAPER.title, correct: 1, total_mcq: 1, percent: 100, mcq: [], descriptive: [],
      note: '', auto_submitted: false, late: false,
    })
    render(<MemoryRouter><MockExamPanel documentIds={['d1']} /></MemoryRouter>)

    fireEvent.click(screen.getByRole('button', { name: 'Start Mock Exam' }))
    expect(mocks.api.createMockExam).toHaveBeenCalledWith({
      difficulty: 'medium', mcq_count: 10, descriptive_count: 0, duration_minutes: 20, document_ids: ['d1'],
    })
    fireEvent.click(await screen.findByLabelText(/2 years/))
    fireEvent.click(screen.getByRole('button', { name: 'Submit exam' }))

    await waitFor(() => expect(mocks.api.submitMockExam).toHaveBeenCalled())
    expect(mocks.api.submitMockExam).toHaveBeenCalledWith(9, { answers: [1], descriptive: [], auto_submitted: false })
    expect(await screen.findByTestId('mock-score')).toHaveTextContent('1 of 1 correct')
  })

  it('submits automatically when the time has already run out', async () => {
    mocks.api.createMockExam.mockResolvedValue(PAPER)
    mocks.api.startMockExam.mockResolvedValue({
      attempt_id: 5, exam_id: 3, deadline: new Date(Date.now() - 1000).toISOString(), duration_seconds: 1200,
    })
    mocks.api.submitMockExam.mockResolvedValue({
      attempt_id: 5, exam_id: 3, exam_title: PAPER.title, correct: 0, total_mcq: 1, percent: 0, mcq: [], descriptive: [],
      note: '', auto_submitted: true, late: true,
    })
    render(<MemoryRouter><MockExamPanel documentIds={['d1']} /></MemoryRouter>)

    fireEvent.click(screen.getByRole('button', { name: 'Start Mock Exam' }))

    await waitFor(() => expect(mocks.api.submitMockExam).toHaveBeenCalledTimes(1))
    expect(mocks.api.submitMockExam.mock.calls[0][1].auto_submitted).toBe(true)
    expect((await screen.findAllByText(/submitted/)).length).toBeGreaterThan(0)
  })
})

describe('MindMapPanel (kept for the code, not shown in the simplified menu)', () => {
  const MAP = {
    id: 4,
    title: 'Mind map from manual.pdf',
    node_count: 2,
    tree: {
      centre: 'manual.pdf',
      branches: [{
        id: 'n1', label: 'Warranty', sources: [{ source_id: 'S1', document_id: 'd1', filename: 'manual.pdf', page_number: 2 }],
        children: [{ id: 'n2', label: 'Two years', sources: [{ source_id: 'S1', document_id: 'd1', filename: 'manual.pdf', page_number: 2 }] }],
      }],
    },
  }

  it('shows the centre, branches with sources, and collapses a branch', async () => {
    mocks.api.createMindMap.mockResolvedValue(MAP)
    render(<MindMapPanel documentIds={['d1']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Create mind map' }))
    expect(await screen.findByText('Two years')).toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: 'Collapse Warranty' })
    fireEvent.click(toggle)
    expect(screen.queryByText('Two years')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand Warranty' })).toHaveAttribute('aria-expanded', 'false')
  })
})

describe('RevisionPanel (kept for the code, not shown in the simplified menu)', () => {
  it('says plainly when there is no quiz data and invents no weak topics', async () => {
    render(<MemoryRouter><RevisionPanel onNavigate={() => {}} /></MemoryRouter>)
    expect(await screen.findByText('No quiz results yet.')).toBeInTheDocument()
    expect(screen.getByText('Take a quiz to find your weak topics')).toBeInTheDocument()
    expect(screen.getByTestId('due-count')).toHaveTextContent('0 flashcards due')
  })
})
