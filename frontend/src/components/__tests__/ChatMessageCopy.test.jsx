import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ChatMessage from '../ChatMessage'

describe('copy answer', () => {
  it('says so when the browser blocks clipboard access (it does not pretend to copy)', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('blocked')) } })
    render(<ChatMessage message={{ id: 4, role: 'assistant', content: 'Copy me', sources: [] }} />)

    fireEvent.click(screen.getByRole('button', { name: /copy answer/i }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Copy failed' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Copied' })).not.toBeInTheDocument()
  })
})
