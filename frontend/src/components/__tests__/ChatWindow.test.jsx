import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ChatWindow from '../ChatWindow'
import ChatInput from '../ChatInput'
import { exampleQuestions } from '../chat/WelcomeScreen'
import { followUpSuggestions } from '../chat/FollowUps'

const READY = [
  { id: 'a', filename: 'warranty.pdf', processing_status: 'ready', page_count: 3 },
  { id: 'b', filename: 'cleaning.pdf', processing_status: 'ready', page_count: 2 },
]

function props(overrides = {}) {
  return {
    messages: [],
    streaming: false,
    loadingHistory: false,
    error: '',
    onSend: vi.fn().mockResolvedValue(true),
    onStop: vi.fn(),
    onRetry: undefined,
    onRegenerate: vi.fn(),
    canRegenerate: true,
    onFeedback: vi.fn(),
    onOpenSource: vi.fn(),
    documents: READY,
    hasDocuments: true,
    scopeLabel: 'Searching all 2 ready PDFs',
    onAttach: undefined,
    uploading: false,
    ...overrides,
  }
}

describe('ChatWindow welcome screen', () => {
  it('offers example questions built from the student\'s PDFs', () => {
    render(<ChatWindow {...props()} />)
    expect(screen.getByRole('heading', { name: 'What would you like to learn from your PDFs?' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Summarize warranty.pdf' })).toBeInTheDocument()
  })

  it('sends an example question when it is clicked', () => {
    const onSend = vi.fn().mockResolvedValue(true)
    render(<ChatWindow {...props({ onSend })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Summarize warranty.pdf' }))
    expect(onSend).toHaveBeenCalledWith('Summarize warranty.pdf')
  })

  it('asks for a PDF when none is ready, with an upload area', () => {
    render(<ChatWindow {...props({ documents: [], hasDocuments: false })} />)
    expect(screen.getByRole('heading', { name: 'Start by adding a PDF' })).toBeInTheDocument()
    expect(screen.getByTestId('pdf-dropzone')).toBeInTheDocument()
    expect(screen.getByLabelText('Your question')).toBeDisabled()
  })

  it('example questions are derived from the documents', () => {
    expect(exampleQuestions(READY)).toContain('Summarize warranty.pdf')
    expect(exampleQuestions([])).toEqual([])
  })
})

describe('ChatWindow conversation', () => {
  const messages = [
    { id: 1, role: 'user', content: 'How long is the warranty?', sources: [] },
    {
      id: 2,
      role: 'assistant',
      content: 'Two years.',
      sources: [{ source_id: 'S1', document_id: 'a', filename: 'warranty.pdf', page_number: 1, relevant_text: 'Two years.' }],
    },
  ]

  it('shows follow-up suggestions after a saved answer', () => {
    render(<ChatWindow {...props({ messages })} />)
    expect(screen.getByLabelText('Follow-up questions')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Summarize the key points of warranty.pdf' })).toBeInTheDocument()
  })

  it('hides follow-ups while an answer is streaming', () => {
    render(<ChatWindow {...props({ messages, streaming: true })} />)
    expect(screen.queryByRole('button', { name: 'Summarize the key points of warranty.pdf' })).not.toBeInTheDocument()
  })

  it('shows an error with a Try again button that retries', () => {
    const onRetry = vi.fn()
    render(<ChatWindow {...props({ messages, error: 'Gemini is temporarily unavailable.', onRetry })} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Gemini is temporarily unavailable.')
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('offers Regenerate only on the latest answer', () => {
    const more = [...messages, { id: 3, role: 'user', content: 'Thanks', sources: [] }, { id: 4, role: 'assistant', content: 'You are welcome.', sources: [] }]
    render(<ChatWindow {...props({ messages: more })} />)
    expect(screen.getAllByRole('button', { name: /regenerate/i })).toHaveLength(1)
  })

  it('shows the loading state for a conversation being opened', () => {
    render(<ChatWindow {...props({ messages: [], loadingHistory: true })} />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading conversation')
  })
})

describe('ChatInput', () => {
  it('sends the trimmed question on Enter and clears the box on success', async () => {
    const onSend = vi.fn().mockResolvedValue(true)
    render(<ChatInput onSend={onSend} />)

    const box = screen.getByLabelText('Your question')
    fireEvent.change(box, { target: { value: '  What is RAG?  ' } })
    fireEvent.keyDown(box, { key: 'Enter' })

    expect(onSend).toHaveBeenCalledWith('What is RAG?')
    await waitFor(() => expect(box).toHaveValue(''))
  })

  it('keeps the text when sending fails, so it can be sent again', async () => {
    const onSend = vi.fn().mockResolvedValue(false)
    render(<ChatInput onSend={onSend} />)

    const box = screen.getByLabelText('Your question')
    fireEvent.change(box, { target: { value: 'Keep me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send question' }))

    await waitFor(() => expect(onSend).toHaveBeenCalledWith('Keep me'))
    expect(box).toHaveValue('Keep me')
  })

  it('does not send empty text, and Shift+Enter adds a new line instead', () => {
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    const box = screen.getByLabelText('Your question')
    expect(screen.getByRole('button', { name: 'Send question' })).toBeDisabled()
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows Stop while an answer streams, and Enter does not stop it', () => {
    const onStop = vi.fn()
    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} onStop={onStop} streaming />)

    fireEvent.keyDown(screen.getByLabelText('Your question'), { key: 'Enter' })
    expect(onSend).not.toHaveBeenCalled()
    expect(onStop).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Stop answering' }))
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('shows which PDFs will be searched', () => {
    render(<ChatInput onSend={vi.fn()} scopeLabel="Searching 2 selected PDFs" />)
    expect(screen.getByTestId('scope-chip')).toHaveTextContent('Searching 2 selected PDFs')
  })

  it('attaches PDFs from the paperclip control', () => {
    const onAttach = vi.fn()
    render(<ChatInput onSend={vi.fn()} onAttach={onAttach} />)
    const input = screen.getByLabelText('Add PDF files')
    const file = new File(['%PDF-1.4'], 'new.pdf', { type: 'application/pdf' })
    fireEvent.change(input, { target: { files: [file] } })
    expect(onAttach).toHaveBeenCalledTimes(1)
  })
})

describe('follow-up suggestions', () => {
  it('uses the source file name in the first suggestion', () => {
    const suggestions = followUpSuggestions('How long?', [{ filename: 'warranty.pdf' }])
    expect(suggestions[0]).toBe('Summarize the key points of warranty.pdf')
    expect(suggestions.length).toBeLessThanOrEqual(3)
  })

  it('still offers general suggestions when there are no sources', () => {
    expect(followUpSuggestions('How long?', []).length).toBeGreaterThan(0)
  })
})
