import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from '../Sidebar'
import { ThemeProvider } from '../../context/ThemeContext'

const mocks = vi.hoisted(() => ({
  api: { listConversations: vi.fn().mockResolvedValue({ conversations: [], total: 0 }) },
}))
vi.mock('../../services/api', () => ({ api: mocks.api, getErrorMessage: (e, f) => f }))

const state = {}
vi.mock('../../context/ChatContext', () => ({
  useAppState: () => state,
}))

const DOCS = [
  { id: 'a', filename: 'warranty.pdf', processing_status: 'ready' },
  { id: 'b', filename: 'cleaning.pdf', processing_status: 'ready' },
  { id: 'c', filename: 'broken.pdf', processing_status: 'failed' },
]

function setup(overrides = {}) {
  Object.assign(state, {
    documents: DOCS,
    selectedDocumentIds: [],
    toggleDocument: vi.fn(),
    setSelectedDocumentIds: vi.fn(),
    uploadFiles: vi.fn().mockResolvedValue([]),
    uploading: { active: false, done: 0, total: 0, currentName: '' },
    conversations: [],
    removeDocument: vi.fn().mockResolvedValue(true),
    ...overrides,
  })
  render(
    <MemoryRouter>
      <ThemeProvider>
        <Sidebar open={false} onClose={() => {}} />
      </ThemeProvider>
    </MemoryRouter>,
  )
}

describe('Sidebar document selection', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('says all ready documents are searched when nothing is selected', () => {
    setup()
    expect(screen.getByTestId('scope-summary')).toHaveTextContent('Searching: All 2 ready documents')
  })

  it('shows how many documents are selected', () => {
    setup({ selectedDocumentIds: ['a'] })
    expect(screen.getByTestId('scope-summary')).toHaveTextContent('Searching: 1 of 2 selected')
  })

  it('Select all picks only the ready documents, not failed ones', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Select all' }))
    expect(state.setSelectedDocumentIds).toHaveBeenCalledWith(['a', 'b'])
  })

  it('Clear resets the selection to all ready documents', () => {
    setup({ selectedDocumentIds: ['a'] })
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(state.setSelectedDocumentIds).toHaveBeenCalledWith([])
  })

  it('checking a document calls toggleDocument with its id', () => {
    setup()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Use warranty.pdf in chat' }))
    expect(state.toggleDocument).toHaveBeenCalledWith('a')
  })

  it('failed documents have no selection checkbox', () => {
    setup()
    expect(screen.queryByRole('checkbox', { name: 'Use broken.pdf in chat' })).not.toBeInTheDocument()
  })
})

describe('Sidebar document removal', () => {
  it('removes a document only after confirmation', async () => {
    setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    fireEvent.click(screen.getByRole('button', { name: 'Remove cleaning.pdf' }))

    expect(window.confirm).toHaveBeenCalled()
    expect(state.removeDocument).toHaveBeenCalledWith('b')
  })

  it('keeps the document when the user cancels', () => {
    setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    fireEvent.click(screen.getByRole('button', { name: 'Remove warranty.pdf' }))

    expect(state.removeDocument).not.toHaveBeenCalled()
  })

  it('every document row has a remove button, including failed ones', () => {
    setup()
    const list = screen.getByText('broken.pdf').closest('li')
    expect(within(list).getByRole('button', { name: 'Remove broken.pdf' })).toBeInTheDocument()
  })
})
