import { describe, expect, it } from 'vitest'
import { getErrorMessage } from '../api'

describe('getErrorMessage', () => {
  it('shows the detail message sent by the backend', () => {
    const error = { response: { status: 400, data: { detail: 'Please type a question first.' } } }
    expect(getErrorMessage(error)).toBe('Please type a question first.')
  })

  it('reads validation details from FastAPI 422 responses', () => {
    const error = { response: { status: 422, data: { detail: [{ msg: 'Field required' }] } } }
    expect(getErrorMessage(error)).toBe('Field required')
  })

  it('explains file size errors without a backend message', () => {
    const error = { response: { status: 413, data: {} } }
    expect(getErrorMessage(error)).toBe('The file is too large to upload.')
  })

  it('explains rate limits', () => {
    const error = { response: { status: 429, data: {} } }
    expect(getErrorMessage(error)).toMatch(/Too many requests/)
  })

  it('uses the fallback when a server error has no readable detail', () => {
    const bare = { response: { status: 500, data: {} } }
    expect(getErrorMessage(bare, 'Fallback text')).toBe('Fallback text')
  })

  it('handles timeouts', () => {
    expect(getErrorMessage({ code: 'ECONNABORTED' })).toMatch(/took too long/)
  })

  it('handles a backend that cannot be reached', () => {
    expect(getErrorMessage({ request: {} })).toMatch(/Cannot reach the server/)
  })

  it('falls back to a generic message for anything else', () => {
    expect(getErrorMessage(new Error('boom'))).toBe('Something went wrong. Please try again.')
  })
})
