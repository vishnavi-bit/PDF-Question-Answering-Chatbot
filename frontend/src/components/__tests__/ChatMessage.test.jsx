import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ChatMessage from '../ChatMessage'
import Markdown from '../chat/Markdown'

const source = {
  source_id: 'S1',
  document_id: 'doc1',
  filename: 'python.pdf',
  page_number: 5,
  relevant_text: 'Lists are mutable sequences.',
  similarity: 0.82,
}

describe('ChatMessage', () => {
  it('shows the user question as plain text', () => {
    render(<ChatMessage message={{ id: 1, role: 'user', content: 'What is a list?' }} />)
    expect(screen.getByText('What is a list?')).toBeInTheDocument()
  })

  it('renders Markdown: bullet points and bold text', () => {
    const message = { id: 2, role: 'assistant', content: 'Key points:\n\n- **Mutable** sequences\n- Ordered items', sources: [] }
    render(<ChatMessage message={message} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.getByText('Mutable').tagName).toBe('STRONG')
  })

  it('shows source cards with the file name and page, and opens the page on click', () => {
    const onOpenSource = vi.fn()
    const message = { id: 3, role: 'assistant', content: 'Lists can change.', sources: [source] }
    render(<ChatMessage message={message} onOpenSource={onOpenSource} />)

    expect(screen.getByTestId('citation-card')).toHaveTextContent('python.pdf')
    expect(screen.getByTestId('citation-card')).toHaveTextContent('Page 5')
    fireEvent.click(screen.getByRole('button', { name: 'Open at page 5' }))
    expect(onOpenSource).toHaveBeenCalledWith(source)
  })

  it('links to the whole document at the cited page in a new tab', () => {
    const message = { id: 3, role: 'assistant', content: 'Lists can change.', sources: [source] }
    render(<ChatMessage message={message} />)
    const link = screen.getByRole('link', { name: /Open document/ })
    expect(link).toHaveAttribute('href', '/api/documents/doc1/file#page=5')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('copies the answer text to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    render(<ChatMessage message={{ id: 4, role: 'assistant', content: 'Copy me', sources: [] }} />)
    fireEvent.click(screen.getByRole('button', { name: /copy answer/i }))

    expect(writeText).toHaveBeenCalledWith('Copy me')
    await waitFor(() => expect(screen.getByRole('button', { name: /copied/i })).toBeInTheDocument())
  })

  it('sends helpful and not helpful feedback', () => {
    const onFeedback = vi.fn()
    render(<ChatMessage message={{ id: 5, role: 'assistant', content: 'Answer', sources: [] }} onFeedback={onFeedback} />)
    fireEvent.click(screen.getByRole('button', { name: 'Helpful answer' }))
    fireEvent.click(screen.getByRole('button', { name: 'Not helpful answer' }))
    expect(onFeedback).toHaveBeenNthCalledWith(1, 5, 'up')
    expect(onFeedback).toHaveBeenNthCalledWith(2, 5, 'down')
  })

  it('offers Regenerate only on the latest answer', () => {
    const onRegenerate = vi.fn()
    const { rerender } = render(
      <ChatMessage message={{ id: 6, role: 'assistant', content: 'Old', sources: [] }} onRegenerate={onRegenerate} isLatestAnswer />,
    )
    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }))
    expect(onRegenerate).toHaveBeenCalledTimes(1)

    rerender(<ChatMessage message={{ id: 6, role: 'assistant', content: 'Old', sources: [] }} onRegenerate={onRegenerate} isLatestAnswer={false} />)
    expect(screen.queryByRole('button', { name: /regenerate/i })).not.toBeInTheDocument()
  })

  it('shows a typing indicator while the answer has not started', () => {
    render(<ChatMessage message={{ id: 'temp', role: 'assistant', content: '', sources: [], pending: true }} />)
    expect(screen.getByRole('status')).toHaveTextContent('Searching your PDFs')
  })

  it('shows sources only after the answer is complete', () => {
    const streaming = { id: 'temp', role: 'assistant', content: 'Partial', sources: [source], pending: true }
    render(<ChatMessage message={streaming} />)
    expect(screen.queryByTestId('citation-card')).not.toBeInTheDocument()
  })

  it('explains a stopped answer that was not saved', () => {
    render(<ChatMessage message={{ id: 'temp', role: 'assistant', content: 'Half an answer', sources: [], stopped: true }} />)
    expect(screen.getByRole('status')).toHaveTextContent('not saved')
  })
})

describe('Markdown', () => {
  it('highlights code blocks', () => {
    const { container } = render(<Markdown text={'```python\ndef hello():\n    return 1\n```'} />)
    expect(container.querySelector('pre code')).not.toBeNull()
    expect(container.querySelector('.hljs-keyword')).not.toBeNull()
  })

  it('does not render raw HTML from the answer', () => {
    const { container } = render(<Markdown text={'Safe <script>alert(1)</script> text'} />)
    expect(container.querySelector('script')).toBeNull()
  })

  it('opens links in a new tab without leaking the opener', () => {
    render(<Markdown text={'[guide](https://example.com/guide)'} />)
    const link = screen.getByRole('link', { name: 'guide' })
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })
})
