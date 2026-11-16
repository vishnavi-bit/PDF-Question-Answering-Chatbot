import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChatMessage from '../ChatMessage'

const base = { id: 5, role: 'assistant', content: 'Motor power is 750 watts. It has a subscription.', sources: [] }

describe('verification note', () => {
  it('warns when some statements could not be matched to the cited text', () => {
    render(<ChatMessage message={{ ...base, verification: { verdict: 'partial', checked: 2, supported: 1, unsupported: 1 } }} />)
    expect(screen.getByRole('status')).toHaveTextContent('could not be matched to the cited PDF text (1 of 2)')
  })

  it('shows no warning when every statement is supported', () => {
    render(<ChatMessage message={{ ...base, verification: { verdict: 'supported', checked: 2, supported: 2, unsupported: 0 } }} />)
    expect(screen.queryByText(/could not be matched/)).not.toBeInTheDocument()
  })

  it('shows no warning for answers that were not checked (for example "Yes.")', () => {
    render(<ChatMessage message={{ ...base, verification: { verdict: 'not_checked', checked: 0, supported: 0, unsupported: 0 } }} />)
    expect(screen.queryByText(/could not be matched/)).not.toBeInTheDocument()
  })
})
