import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useChat } from '../useChat'

const mocks = vi.hoisted(() => ({
  streamChat: vi.fn(),
  streamRegenerate: vi.fn(),
  api: { getConversation: vi.fn(), setMessageFeedback: vi.fn() },
}))
vi.mock('../../services/streamChat', () => ({ streamChat: mocks.streamChat, streamRegenerate: mocks.streamRegenerate }))
vi.mock('../../services/api', () => ({
  api: mocks.api,
  getErrorMessage: (error, fallback) => (error && error.message) || fallback,
}))

const SAVED = (id, content) => ({ id, role: 'assistant', content, sources: [] })
const USER = (id, content) => ({ id, role: 'user', content, sources: [] })

const DONE = {
  conversation_id: 9,
  user_message: USER(101, 'How long?'),
  assistant_message: SAVED(102, 'Two years.'),
  answered_from_documents: true,
  retrieval: {},
}

/** A stream that delivers the given pieces, then finishes with DONE. */
function streamingReply(pieces, done = DONE) {
  return (payload, handlers) => {
    for (const piece of pieces) handlers.onDelta(piece)
    return Promise.resolve(done)
  }
}

beforeEach(() => {
  mocks.streamChat.mockReset()
  mocks.streamRegenerate.mockReset()
  mocks.api.getConversation.mockReset()
  mocks.api.setMessageFeedback.mockReset()
})

describe('useChat sending', () => {
  it('shows the question at once, streams the answer, then keeps the saved messages', async () => {
    mocks.streamChat.mockImplementation(streamingReply(['Two ', 'years.']))
    const { result } = renderHook(() => useChat({}))

    let outcome
    await act(async () => {
      outcome = await result.current.send('How long?')
    })

    expect(outcome).toBe(true)
    expect(result.current.messages.map((m) => m.id)).toEqual([101, 102])
    expect(result.current.messages[1].content).toBe('Two years.')
    expect(result.current.streaming).toBe(false)
    expect(result.current.lastQuestion).toBe('')
  })

  it('shows partial text while the answer is still arriving', async () => {
    let finish
    mocks.streamChat.mockImplementation((payload, handlers) => {
      handlers.onDelta('Two ')
      return new Promise((resolve) => {
        finish = () => resolve(DONE)
      })
    })
    const { result } = renderHook(() => useChat({}))

    act(() => {
      result.current.send('How long?')
    })
    await waitFor(() => expect(result.current.messages.some((m) => m.pending && m.content === 'Two ')).toBe(true))
    expect(result.current.streaming).toBe(true)
    expect(result.current.canRegenerate).toBe(false)

    await act(async () => finish())
    expect(result.current.streaming).toBe(false)
  })

  it('sends a unique request id with every question', async () => {
    mocks.streamChat.mockImplementation(streamingReply(['ok']))
    const { result } = renderHook(() => useChat({}))

    await act(async () => {
      await result.current.send('first')
      await result.current.send('second')
    })

    const ids = mocks.streamChat.mock.calls.map(([payload]) => payload.client_request_id)
    expect(ids[0]).toBeTruthy()
    expect(ids[1]).toBeTruthy()
    expect(ids[0]).not.toBe(ids[1])
  })

  it('sends the selected PDFs and the answer length', async () => {
    mocks.streamChat.mockImplementation(streamingReply(['ok']))
    window.localStorage.setItem('pdfbot-answer-style', 'short')
    const { result } = renderHook(() => useChat({ documentIds: ['doc-1'] }))

    await act(async () => {
      await result.current.send('Q')
    })

    const payload = mocks.streamChat.mock.calls[0][0]
    expect(payload.document_ids).toEqual(['doc-1'])
    expect(payload.answer_style).toBe('short')
    window.localStorage.clear()
  })

  it('keeps the partial text when the student presses Stop, and marks it as not saved', async () => {
    mocks.streamChat.mockImplementation((payload, handlers, options) => {
      handlers.onDelta('The warranty ')
      return new Promise((resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(Object.assign(new Error('Aborted'), { name: 'AbortError' })))
      })
    })
    const { result } = renderHook(() => useChat({}))

    let outcome
    let sending
    act(() => {
      sending = result.current.send('How long?').then((value) => {
        outcome = value
      })
    })
    await waitFor(() => expect(result.current.streaming).toBe(true))
    await waitFor(() => expect(result.current.messages.some((m) => m.content === 'The warranty ')).toBe(true))
    act(() => result.current.stop())
    await act(async () => {
      await sending
    })

    expect(outcome).toBe(false)
    const stopped = result.current.messages.find((m) => m.stopped)
    expect(stopped.content).toBe('The warranty ')
    expect(stopped.id).toMatch(/^temp-/) // never replaced by a saved message
    expect(result.current.error).toBe('')
  })

  it('removes the question on a failure, shows the message, and remembers it for Retry', async () => {
    mocks.streamChat.mockRejectedValueOnce(new Error('Gemini is temporarily unavailable. Please try again in about 45 seconds.'))
    const { result } = renderHook(() => useChat({}))

    await act(async () => {
      await result.current.send('How long?')
    })

    expect(result.current.messages).toEqual([])
    expect(result.current.error).toContain('temporarily unavailable')
    expect(result.current.lastQuestion).toBe('How long?')
  })

  it('Retry sends the same question again', async () => {
    mocks.streamChat
      .mockRejectedValueOnce(new Error('Gemini is busy.'))
      .mockImplementationOnce(streamingReply(['Two years.']))
    const { result } = renderHook(() => useChat({}))

    await act(async () => {
      await result.current.send('How long?')
    })
    await act(async () => {
      await result.current.retry()
    })

    expect(mocks.streamChat).toHaveBeenCalledTimes(2)
    expect(mocks.streamChat.mock.calls[1][0].question).toBe('How long?')
    expect(result.current.error).toBe('')
  })

  it('does not start a second answer while one is running', async () => {
    mocks.streamChat.mockImplementation(() => new Promise(() => {}))
    const { result } = renderHook(() => useChat({}))

    act(() => {
      result.current.send('first')
    })
    let second
    await act(async () => {
      second = await result.current.send('second')
    })

    expect(second).toBe(false)
    expect(mocks.streamChat).toHaveBeenCalledTimes(1)
  })

  it('reports a new conversation id once it is created', async () => {
    mocks.streamChat.mockImplementation(streamingReply(['ok']))
    const onConversationCreated = vi.fn()
    const { result } = renderHook(() => useChat({ onConversationCreated }))

    await act(async () => {
      await result.current.send('Q')
    })

    expect(onConversationCreated).toHaveBeenCalledWith(9)
  })
})

describe('useChat regenerate', () => {
  async function loadConversation() {
    mocks.api.getConversation.mockResolvedValue({
      id: 9,
      messages: [USER(1, 'How long?'), SAVED(2, 'Two years, old answer.')],
    })
    const hook = renderHook(() => useChat({ conversationId: 9 }))
    await waitFor(() => expect(hook.result.current.messages.length).toBe(2))
    return hook
  }

  it('replaces the latest answer only when the new one succeeds', async () => {
    const { result } = await loadConversation()
    mocks.streamRegenerate.mockImplementation(streamingReply(['Two ', 'years, new.'], { ...DONE, assistant_message: SAVED(2, 'Two years, new.') }))

    await act(async () => {
      await result.current.regenerate()
    })

    expect(result.current.messages[1].content).toBe('Two years, new.')
    expect(result.current.messages).toHaveLength(2)
  })

  it('keeps the original answer when regenerate fails', async () => {
    const { result } = await loadConversation()
    mocks.streamRegenerate.mockRejectedValue(new Error('Gemini did not finish the answer in time.'))

    await act(async () => {
      await result.current.regenerate()
    })

    expect(result.current.messages[1].content).toBe('Two years, old answer.')
    expect(result.current.error).toContain('did not finish')
  })

  it('is not offered while an answer is streaming', async () => {
    const { result } = await loadConversation()
    expect(result.current.canRegenerate).toBe(true)
    mocks.streamRegenerate.mockImplementation(() => new Promise(() => {}))

    act(() => {
      result.current.regenerate()
    })
    await waitFor(() => expect(result.current.streaming).toBe(true))
    expect(result.current.canRegenerate).toBe(false)
  })
})

describe('useChat feedback', () => {
  it('saves the choice and removes it when clicked again', async () => {
    mocks.api.getConversation.mockResolvedValue({ id: 9, messages: [SAVED(2, 'Answer')] })
    mocks.api.setMessageFeedback.mockResolvedValue({})
    const { result } = renderHook(() => useChat({ conversationId: 9 }))
    await waitFor(() => expect(result.current.messages.length).toBe(1))

    await act(async () => result.current.setFeedback(2, 'up'))
    expect(result.current.messages[0].feedback).toBe('up')
    expect(mocks.api.setMessageFeedback).toHaveBeenLastCalledWith(2, 'up')

    await act(async () => result.current.setFeedback(2, 'up'))
    expect(result.current.messages[0].feedback).toBeNull()
    expect(mocks.api.setMessageFeedback).toHaveBeenLastCalledWith(2, null)
  })
})
