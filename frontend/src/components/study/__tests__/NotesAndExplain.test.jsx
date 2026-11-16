import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import NotesPanel from '../NotesPanel'
import ExplainPanel from '../ExplainPanel'
import { openStudySource } from '../StudyCitations'

const mocks = vi.hoisted(() => ({
  api: {
    saveNotes: vi.fn(),
    updateSavedNotes: vi.fn(),
    explainTopic: vi.fn(),
    documentFileUrl: (id) => `/api/documents/${id}/file`,
  },
  getErrorMessage: (error, fallback) => (error && error.message) || fallback,
}))
vi.mock('../../../services/api', () => mocks)

const SOURCE = { source_id: 'S1', document_id: 'abc', filename: 'manual.pdf', page_number: 3 }
const NOTE = {
  id: 11,
  title: 'Overview notes from manual.pdf',
  mode: 'overview',
  length: 'detailed',
  document_ids: ['d1'],
  body: {
    overview: 'The blender has a two year warranty.',
    key_points: [{ text: 'The motor is 750 watts.', sources: [SOURCE] }],
    definitions: [{ term: 'Warranty', meaning: 'A promise to repair the product.', sources: [SOURCE] }],
    chapters: [],
    simple_explanations: [],
  },
}

beforeEach(() => {
  mocks.api.saveNotes.mockReset()
  mocks.api.updateSavedNotes.mockReset()
  mocks.api.explainTopic.mockReset()
})

describe('NotesPanel (simplified)', () => {
  it('generates detailed notes by default and shows the overview and points with pages', async () => {
    mocks.api.saveNotes.mockResolvedValue(NOTE)
    render(<NotesPanel documentIds={['d1']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Generate Notes' }))
    expect(await screen.findByLabelText('Overview')).toHaveValue('The blender has a two year warranty.')
    expect(screen.getByText(/The motor is 750 watts/)).toBeInTheDocument()
    expect(mocks.api.saveNotes).toHaveBeenCalledWith({ mode: 'overview', length: 'detailed', document_ids: ['d1'] })
  })

  it('sends Short when Short is chosen', async () => {
    mocks.api.saveNotes.mockResolvedValue({ ...NOTE, length: 'short' })
    render(<NotesPanel documentIds={[]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Short' }))
    fireEvent.click(screen.getByRole('button', { name: 'Generate Notes' }))
    await waitFor(() => expect(mocks.api.saveNotes).toHaveBeenCalledWith({ mode: 'overview', length: 'short', document_ids: [] }))
  })

  it('saves an edited overview and title', async () => {
    mocks.api.saveNotes.mockResolvedValue(NOTE)
    mocks.api.updateSavedNotes.mockResolvedValue({ ...NOTE, title: 'My notes' })
    render(<NotesPanel documentIds={['d1']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Generate Notes' }))
    fireEvent.change(await screen.findByLabelText('Notes title'), { target: { value: 'My notes' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(mocks.api.updateSavedNotes).toHaveBeenCalledWith(11, expect.objectContaining({ title: 'My notes' })))
    expect(await screen.findByText('Changes saved.')).toBeInTheDocument()
  })

  it('shows the server error message when notes cannot be created', async () => {
    mocks.api.saveNotes.mockRejectedValue(new Error('Gemini is temporarily unavailable.'))
    render(<NotesPanel documentIds={[]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Generate Notes' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Gemini is temporarily unavailable.')
  })
})

describe('ExplainPanel (simplified)', () => {
  it('shows the explanation, example and citation when found', async () => {
    mocks.api.explainTopic.mockResolvedValue({
      topic: 'warranty', found: true, explanation: 'A warranty is a promise to repair.', example: 'A blender is repaired for free.',
      sources: [SOURCE],
    })
    render(<ExplainPanel documentIds={['d1']} />)
    fireEvent.change(screen.getByLabelText('Topic to explain'), { target: { value: 'warranty' } })
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    expect(await screen.findByText('A warranty is a promise to repair.')).toBeInTheDocument()
    expect(screen.getByText('A blender is repaired for free.')).toBeInTheDocument()
    expect(screen.getAllByText(/manual\.pdf/).length).toBeGreaterThan(0)
    expect(screen.queryByLabelText(/follow-up/i)).toBeNull()
  })

  it('does not call the server for a one-letter topic', () => {
    render(<ExplainPanel documentIds={[]} />)
    fireEvent.change(screen.getByLabelText('Topic to explain'), { target: { value: 'a' } })
    fireEvent.click(screen.getByRole('button', { name: 'Explain' }))
    expect(screen.getByRole('alert')).toHaveTextContent('at least two letters')
    expect(mocks.api.explainTopic).not.toHaveBeenCalled()
  })
})

describe('openStudySource', () => {
  afterEach(() => vi.restoreAllMocks())

  it('builds the PDF URL with the page number', () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    openStudySource({ document_id: 'abc', page_number: 9 })
    expect(open).toHaveBeenCalledWith('/api/documents/abc/file#page=9', '_blank', 'noopener,noreferrer')
  })
})
